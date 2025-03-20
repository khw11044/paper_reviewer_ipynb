import os 
import re
import glob
import base64
from markdownify import markdownify as markdown

from utils.Classes import GraphState, LayoutAnalyzer
from utils.funcs import *
from utils.extracts import *
from utils.crops import *
from utils.creates import *
from utils.save import save_results

from utils.creates import create_text_trans_summary
from utils.vectordb import build_db
from utils.prompt import summary_prompt, map_prompt, trans_prompt

from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.environ.get("UPSTAGE_API_KEY")
analyzer = LayoutAnalyzer(OPENAI_API_KEY)

def paper_analysis(state):
    
    # 파일 업데이트
    split_file_list = split_pdf(state)
    state.update(split_file_list)
    
    # 논문 분석 
    state_out = analyze_layout(analyzer, state)
    state.update(state_out)
    
    state_out = extract_page_metadata(state)
    state.update(state_out)
    
    state_out = extract_page_elements(state)
    state.update(state_out)
    
    state_out = extract_tag_elements_per_page(state)
    state.update(state_out)
    
    state_out = page_numbers(state)
    state.update(state_out)
    
    state_out = crop_image(state)
    state.update(state_out)
    
    state_out = crop_table(state)
    state.update(state_out)

    state_out = crop_equation(state)
    state.update(state_out)

    state_out = extract_page_text(state)
    state.update(state_out)
    
    return state

def paper_analysis_gen(state,text_summary_chain,paper_summary_chain,trans_chain):
    # 생성 (통번역, 영어 요약, 한국어 요약)

    # 텍스트 요약 생성
    state_out = create_text_summary(text_summary_chain, state)
    state.update(state_out)

    state_out = map_reduce_summary(paper_summary_chain, state)
    state.update(state_out)

    # 요약 번역
    trans_chain = get_translator(selected_model, trans_prompt)
    state_out = create_text_trans_summary(trans_chain, state)
    state.update(state_out)

    # Image 요약 생성 
    state_out = create_image_summary_data_batches(state)
    state.update(state_out)

    state_out = create_image_summary(state)
    state.update(state_out)

    # Table 요약 생성 
    state_out = create_table_summary_data_batches(state)
    state.update(state_out)


    state_out = create_table_summary(state)
    state.update(state_out)

    # Equation 요약 생성 
    state_out = create_equation_summary_data_batches(state)
    state.update(state_out)

    state_out = create_equation_summary(state)
    state.update(state_out)

    # 4 표를 다시 마크다운 표 생성 
    state_out = create_table_markdown(state)
    state.update(state_out)

    return state


if __name__=="__main__":
    file_path = './papers/objectvla.pdf'
    selected_model = 'gpt-4o-mini'
    
    text_summary_chain = get_chain(selected_model, summary_prompt)
    paper_summary_chain = get_chain(selected_model, map_prompt)
    trans_chain = get_translator(selected_model, trans_prompt)
    
    state = GraphState(filepath=file_path, batch_size=10)
    
    # 1. 파일 업데이트
    split_file_list = split_pdf(state)
    state.update(split_file_list)
    
    # 2. 논문 분석 
    state = paper_analysis(state)
    
    pdf_file = state["filepath"]  # PDF 파일 경로
    output_folder = os.path.splitext(pdf_file)[0]  # 출력 폴더 경로 설정
    filename = os.path.basename(pdf_file).split('.')[0]
    md_output_file1 = save_results(output_folder, filename, state['html_content'])
    print(md_output_file1)


    # 3. 분석을 위한 생성 
    state = paper_analysis_gen(state,text_summary_chain,paper_summary_chain,trans_chain)
    
    # 수식 이미지 처리
    cnt = 1
    for key, value in state['equation_summary'].items():
        equation_html = f"<p id='{key}_1' data-category='equation' style='font-size:14px'>{value}</p>"
        state['html_content'].insert(cnt+int(key), equation_html)
        cnt+=1

    # 생성 내용 분석 파일에 덮어써서 저장
    md_output_file = save_results(output_folder, filename, state['html_content'])
    print(md_output_file)
    
    # 분석결과 저장
    output_file = f"{output_folder}/{filename}_analy.json" 
    with open(output_file, "w", encoding='utf-8') as file:
        json.dump(state, file, ensure_ascii=False)


    # 분석 번역 요약 과정에서 생긴 json 파일 제거 
    for del_file in state['split_filepaths'] + state['analyzed_files']:
        os.remove(del_file)


    # 4. 결과 마크다운으로 생성 
    
    # 4.1 통번역 결과
    original_paper_md = f"{output_folder}/{filename}.md"
    new_docs = load_and_split(original_paper_md)
    translated_paragraph = ['# ' + new_docs[0].metadata['Header 1']] + trans_chain.batch(new_docs[1:])
    combined_content = "\n".join(translated_paragraph)
    md_output = markdown(combined_content)

    trans_paper_md = f"{output_folder}/{filename}_trans.md"
    with open(trans_paper_md, "w", encoding="utf-8") as f:
        f.write(md_output)

    print(trans_paper_md)


    # 4.2 영어 요약 
    with open(output_file, "r", encoding='utf-8') as f:
        json_data = json.load(f)
        
    markdown_contents = []  # 마크다운 내용을 저장할 빈 리스트
    
    names = json_data['section_names']
    for i, page in enumerate(json_data['texts_summary'].keys()):
        page = int(page)
        if names[page] == 'References':
            continue
        print(names[page])
        text_summary = json_data['texts_summary'][str(page)]
        section_title = f'# {names[page]}'
        if i==0:
            text_summary = json_data['paper_summary']
        
        markdown_contents.append(section_title)
        markdown_contents.append(text_summary)
        
        for image_summary_data_batch in json_data['image_summary_data_batches']:
            if image_summary_data_batch['page'] == page:
                img_file = image_summary_data_batch['image'].split('/')[-1]
                img_name = os.path.basename(img_file).split('.')[0]

                # 이미지와 테이블 마크다운을 리스트에 추가
                markdown_contents.append(f'\n ![{img_name}]({img_file}) \n')
                
        for table_summary_data_batch in json_data['table_summary_data_batches']:
            if table_summary_data_batch['page'] == page:
                table_img_file = table_summary_data_batch['table'].split('/')[-1]
                table_text = table_summary_data_batch['text']
                
                table_img_name = os.path.basename(table_img_file).split('.')[0]

                # 테이블과 텍스트도 리스트에 추가
                markdown_contents.append(f'\n ![{table_img_name}]({table_img_file}) \n')


    # summary 마크다운 저장하기 
    markdown_file_path = f'{output_folder}/{filename}_summary_en.md'
    with open(markdown_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(markdown_contents))
        

    # 4.3 한국어 요약
    markdown_contents = []
    for i, page in enumerate(json_data['texts_summary'].keys()):
        page = int(page)
        if names[page] == 'References':
            continue
        print(names[page])
        if i == 0:
            text_summary = json_data['paper_trans_summary']
        else:
            text_summary = json_data['texts_trans_summary'][str(page)]
            
        section_title = f'# {names[page]}'
        
        markdown_contents.append(section_title)
        markdown_contents.append(text_summary)
        
        for image_summary_data_batch in json_data['image_summary_data_batches']:
            if image_summary_data_batch['page'] == page:
                img_file = image_summary_data_batch['image'].split('/')[-1]
                img_name = os.path.basename(img_file).split('.')[0]
                
                # 이미지와 테이블 마크다운을 리스트에 추가
                markdown_contents.append(f'![{img_name}]({img_file})')

                
        for table_summary_data_batch in json_data['table_summary_data_batches']:
            if table_summary_data_batch['page'] == page:
                table_img_file = table_summary_data_batch['table'].split('/')[-1]
                table_text = table_summary_data_batch['text']
                table_img_name = os.path.basename(table_img_file).split('.')[0]
            
                # 테이블과 텍스트도 리스트에 추가
                markdown_contents.append(f'![{table_img_name}]({table_img_file})')

    markdown_file_path = f'{output_folder}/{filename}_summary_ko.md'
    with open(markdown_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(markdown_contents))
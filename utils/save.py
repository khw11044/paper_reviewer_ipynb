import os
import re
from bs4 import BeautifulSoup
import markdownify
from markdownify import markdownify as markdown

def format_text(text):
    # .\n을 `. \n`으로 변경
    text = re.sub(r'\.\n', r'. \n', text)
    
    
    match = re.search(r'(References\n[=-]+\n.*?)(?=\n\n\d+\.|\Z)', text, re.DOTALL | re.IGNORECASE)
    
    if match:
        # References 섹션 전 부분
        a_before = text[:match.start()]
        
        # References 섹션
        b = match.group(1)
        
        # References 이후의 부분 (예: 7. Appendix 등)
        a_after = text[match.end():]
        
        # a_before와 a_after를 결합
        a = a_before + a_after
        
        return a, b
    
    # References 섹션을 찾지 못한 경우
    return text, ""





def save_results(output_folder, filename, html_content):
    
    # 1. HTML 파일 저장
    html_output_file = os.path.join(output_folder, f"{filename}.html")
    combined_html_content = "\n".join(html_content)
    soup = BeautifulSoup(combined_html_content, "html.parser")
    all_tags = set([tag.name for tag in soup.find_all()])
    html_tag_list = [tag for tag in list(all_tags) if tag not in ["br"]]

    with open(html_output_file, "w", encoding="utf-8") as f:
        f.write(combined_html_content)
    
    print(f"HTML 파일이 {html_output_file}에 저장되었습니다.")
    
    # 2. Markdown 파일 저장
    md_output_file = os.path.join(output_folder, f"{filename}.md")
    md_output = markdown(
        combined_html_content,
        convert=html_tag_list,
        heading_style=markdownify.ATX
    )
    
    # md_output = format_markdown_headers(md_output)

    with open(md_output_file, "w", encoding="utf-8") as f:
        f.write(md_output)

    print(f"Markdown 파일이 {md_output_file}에 저장되었습니다.")
    
    return md_output_file


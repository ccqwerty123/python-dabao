import requests

# 假设文本文件名为 urls.txt，并位于仓库根目录
URLS_FILE = 'urls.txt'
HEADERS = {
    'User-Agent': 'Your User Agent'  # 替换为你的User-Agent
}

def visit_urls(urls_file):
    with open(urls_file, 'r') as file:
        urls = [line.strip() for line in file if line.strip()]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS)
            print(f'Successfully visited {url} with status code: {response.status_code}')
        except requests.RequestException as e:
            print(f'An error occurred while visiting {url}: {e}')

if __name__ == '__main__':
    visit_urls(URLS_FILE)

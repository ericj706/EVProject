import os

from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace css
with open('style.css', 'r', encoding='utf-8') as f:
    css = f.read()
html = html.replace('<link rel="stylesheet" href="style.css">', f'<style>{css}</style>')

# Replace js files
for js_file in ['data.js', 'heatmap.js', 'existing_stations.js', 'baseline_data.js', 'script.js']:
    with open(js_file, 'r', encoding='utf-8') as f:
        js = f.read()
    html = html.replace(f'<script src="{js_file}"></script>', f'<script>{js}</script>')

with open('index_single_file.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Successfully bundled everything into index_single_file.html')

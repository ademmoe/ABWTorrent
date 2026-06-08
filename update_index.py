import re

with open('templates/index.html', 'r') as f:
    content = f.read()

# Remove specific nav from index
content = re.sub(r'<nav class="indigo">.*?</nav>\s*', '', content, flags=re.DOTALL)

# Remove specific main container styling that might conflict
content = re.sub(r'<main class="container" style="padding-top: 2rem;">', '<div class="container" style="padding-top: 2rem;">', content)
content = re.sub(r'</main>', '</div>', content)

with open('templates/index.html', 'w') as f:
    f.write(content)

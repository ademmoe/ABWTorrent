import re

with open('templates/settings.html', 'r') as f:
    content = f.read()

# Replace block body_class
content = re.sub(r'{% block body_class %}has-sidebar{% endblock %}\s*', '', content)

# Remove manual Navbar, Sidebar, and Main tags
content = re.sub(r'<!-- Navbar -->\s*<header>.*?</header>\s*', '', content, flags=re.DOTALL)
content = re.sub(r'<!-- Sidebar -->\s*<ul id="slide-out".*?</ul>\s*', '', content, flags=re.DOTALL)
content = re.sub(r'<!-- Main Content -->\s*<main[^>]*>', '', content)
content = re.sub(r'</main>\s*(?={% endblock %})', '', content)

with open('templates/settings.html', 'w') as f:
    f.write(content)

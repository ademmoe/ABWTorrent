import re

with open('templates/base.html', 'r') as f:
    content = f.read()

# Replace CSS
content = re.sub(
    r'\s*\.sidenav-fixed \{.*?\n\s*\}\s*body\.has-sidebar.*?\}\s*body\.has-sidebar\.sidebar-closed.*?\}\s*@media only screen and \(max-width: 992px\) \{.*?\n\s*\}',
    '', content, flags=re.DOTALL
)

# Replace the navbar
new_navbar = """  <!-- Navbar Header -->
  <header>
    <nav class="indigo top-nav">
      <div class="nav-wrapper" style="padding: 0 2rem;">
        <a href="{{ url_for('index') }}" class="brand-logo left" style="padding-left: 0 !important;">{% block page_title %}ABWTorrent{% endblock %}</a>
        {% if session.get('user') %}
        <ul class="left" style="margin-left: 180px;">
          <li><span style="font-size: 1.1rem;">Logged in as: <strong>{{ session.get('user') }}</strong></span></li>
        </ul>
        <ul class="right hide-on-med-and-down">
          <li><a href="{{ url_for('dashboard') }}" class="waves-effect"><i class="material-icons left">dashboard</i>Dashboard</a></li>
          <li><a href="{{ url_for('settings') }}" class="waves-effect"><i class="material-icons left">settings</i>Settings</a></li>
          <li><a href="{{ url_for('logout') }}" class="waves-effect"><i class="material-icons left">exit_to_app</i>Sign out</a></li>
        </ul>
        {% else %}
        <ul class="right hide-on-med-and-down">
          <li><a href="{{ url_for('dashboard') }}">Admin Login</a></li>
        </ul>
        {% endif %}
      </div>
    </nav>
  </header>"""

content = re.sub(
    r'<!-- Navbar Header -->.*?</header>',
    new_navbar, content, flags=re.DOTALL
)

# Remove sidebar block
content = re.sub(r'<!-- Sidebar -->\s*{% block sidebar %}{% endblock %}\s*', '', content)

with open('templates/base.html', 'w') as f:
    f.write(content)

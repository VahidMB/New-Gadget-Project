# ruff: noqa: E402
"""Export safe, static previews from the actual local demo templates."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "gadget_server.demo_settings"
import django

django.setup()
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import Client
from core.models import WordPressDevice

css = (ROOT / "backend/core/static/core/console.css").read_text()
output = ROOT / "docs/previews"
output.mkdir(exist_ok=True)
views = [("personal", "maryam", "/panel/", "پنل شخصی"), ("company", "aria", "/panel/", "پنل شرکت"), ("admin", "admin", "/panel/", "پنل مدیر"), ("monitoring", "admin", "/panel/monitoring/", "پایش سرویس‌ها")]
if "--settings-panels" in sys.argv:
    device = WordPressDevice.objects.filter(assigned_user__username="maryam").first()
    if device is None:
        raise RuntimeError("Seed the demo before exporting settings panels")
    views = [("buzzer", "maryam", f"/panel/devices/{device.pk}/buzzer/new/", "قانون بازر"), ("sources-settings", "admin", "/panel/data-sources/new/", "منبع اطلاعات"), ("connections", "admin", "/panel/connections/", "ارتباطات"), ("integration-settings", "admin", "/panel/integrations/new/", "توکن و API")]
fragments = []
for key, username, url, label in views:
    client = Client()
    client.force_login(get_user_model().objects.get(username=username))
    response = client.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"Preview failed: {key}: {response.status_code}")
    soup = BeautifulSoup(response.content, "html.parser")
    for node in soup.select('script, input[name="csrfmiddlewaretoken"]'):
        node.decompose()
    for node in soup.select('[data-live-url]'):
        del node['data-live-url']
    for form in soup.select('form'):
        form['onsubmit'] = 'return false'
    for node in soup.select('[onchange]'):
        del node['onchange']
    for node in soup.select('a'):
        node['href'] = '#'
        node['onclick'] = 'return false'
    css_tag = soup.new_tag('style')
    css_tag.string = css
    soup.head.append(css_tag)
    for link in soup.select('link[rel="stylesheet"]'):
        link.decompose()
    script = soup.new_tag('script')
    script.string = "document.querySelectorAll('[data-theme-toggle]').forEach(b=>b.onclick=()=>document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark');document.querySelector('[data-menu]')?.addEventListener('click',()=>document.querySelector('.sidebar').classList.toggle('open'));"
    soup.body.append(script)
    (output / f"{key}.html").write_text(str(soup))
    script.decompose()
    for node in soup.body.select('[class]'):
        node['class'] = ['gp-' + value for value in node['class']]
    # IDs from repeated templates must remain unique in the conversation preview.
    for node in soup.body.select('[id]'):
        old = node['id']
        node['id'] = key + '-' + old
        for label_node in soup.body.select(f'label[for="{old}"]'):
            label_node['for'] = key + '-' + old
    fragment = f'<section data-preview="{key}"'+(' hidden' if key != views[0][0] else '')+'>'+''.join(str(node) for node in soup.body.contents)+'</section>'
    fragments.append(fragment)

# Keep the product's styling; isolate it from the conversation's own UI utilities.
scoped = re.sub(r'\.([a-zA-Z_][\w-]*)', r'.gp-\1', css)
scoped = scoped.replace('html[data-theme=dark]', ':scope[data-theme=dark]').replace(':root', ':scope')
scoped = re.sub(r'\bbody\b', ':scope', scoped)
scoped = re.sub(r'--([a-zA-Z][\w-]*)', r'--gp-\1', scoped)
scoped += '\n.gp-shell{min-height:0}.gp-sidebar{position:relative;top:auto;height:auto;overflow:visible}.gp-content{padding:26px}.gp-topbar{padding:0 26px}[data-preview][hidden]{display:none!important}.gp-preview-tabs{display:flex;flex-wrap:wrap;gap:8px;padding:14px;background:var(--gp-surface);border-bottom:1px solid var(--gp-line)}.gp-preview-tabs button{padding:7px 16px;border:1px solid var(--gp-line);border-radius:10px;background:var(--gp-surface2);color:var(--gp-ink)}.gp-preview-tabs button[aria-pressed=true]{background:var(--gp-brand);color:white}@media(max-width:760px){.gp-sidebar{display:none;transform:none}.gp-sidebar.gp-open{display:flex}.gp-shell{display:block}.gp-content{padding:18px}}'
controls = '<div class="gp-preview-tabs" role="group" aria-label="انتخاب پنل">'+''.join(f'<button type="button" data-show="{key}" aria-pressed="{str(key == views[0][0]).lower()}">{label}</button>' for key, _, _, label in views)+'</div>'
fragment_path = ROOT.parent / ('gadget-settings-preview.html' if '--settings-panels' in sys.argv else 'gadget-panels-preview.html')
fragment_path.write_text('<div id="gadget-panels-preview" dir="rtl" data-theme="light"><style>@scope (#gadget-panels-preview){'+scoped+'}</style>'+controls+''.join(fragments)+'''</div>
<script>
(() => {
 const root = document.getElementById('gadget-panels-preview');
 root.querySelectorAll('[data-show]').forEach(button => button.addEventListener('click', () => {
  root.querySelectorAll('[data-preview]').forEach(view => view.hidden = view.dataset.preview !== button.dataset.show);
  root.querySelectorAll('[data-show]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
 }));
 root.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
 }));
 root.querySelectorAll('[data-menu]').forEach(button => button.addEventListener('click', () => {
  button.closest('.gp-shell').querySelector('.gp-sidebar').classList.toggle('gp-open');
 }));
})();
</script>
''')
print(f"Exported {len(views)} sanitized demo previews; inline preview: {fragment_path}")

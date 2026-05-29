import os
import glob

nav_item = """          <a href="suppliers.html" data-page="suppliers"
            class="nav-link nav-btn flex items-center gap-3 w-full px-4 py-3 rounded-xl text-sm">
            <span class="material-symbols-outlined text-xl">local_shipping</span> Suppliers
          </a>
"""

for filepath in glob.glob('frontend/*.html'):
    with open(filepath, 'r') as f:
        content = f.read()
    
    if '<a href="inventory.html"' in content and 'suppliers.html' not in content:
        # Insert after Inventory link
        parts = content.split('<a href="inventory.html"')
        # We need to find the end of the inventory link (</a>)
        if len(parts) > 1:
            end_tag = '</a>'
            idx = parts[1].find(end_tag)
            if idx != -1:
                idx += len(end_tag)
                new_part1 = parts[1][:idx] + "\n" + nav_item + parts[1][idx:]
                new_content = parts[0] + '<a href="inventory.html"' + new_part1
                with open(filepath, 'w') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")

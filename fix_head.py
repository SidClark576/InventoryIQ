import glob
import re

files = glob.glob('/Users/sidneyordonia/Documents/InventoryIQ/frontend/*.html')
for file in files:
    with open(file, 'r') as f:
        content = f.read()

    pattern = re.compile(
        r'<script src="https://cdn\.tailwindcss\.com\?plugins=forms,container-queries"></script>\s*'
        r'<link href="https://fonts\.googleapis\.com/css2\?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet" />\s*'
        r'<link href="https://fonts\.googleapis\.com/css2\?family=Material\+Symbols\+Outlined:wght,FILL@100\.\.700,0\.\.1&display=swap"\s*rel="stylesheet" />\s*'
        r'<script>\s*tailwind\.config = \{.*?\}\s*</script>',
        re.DOTALL
    )
    
    replacement = """  <script>
    tailwind.config = {
      theme: { extend: { fontFamily: { sans: ['Inter', 'sans-serif'] }, colors: { brand: '#005ab4' } } }
    }
  </script>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet" />
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
    rel="stylesheet" />"""
    
    new_content, count = re.subn(pattern, replacement, content)
    if count > 0:
        print(f"Fixed {file}")
        with open(file, 'w') as f:
            f.write(new_content)

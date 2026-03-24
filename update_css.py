import codecs

with codecs.open('c:\\InventoryIQ\\index.html', 'r', 'utf-8') as f:
    html = f.read()

new_head = """
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>InventoryIQ</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  
  <style>
    :root {
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --secondary: #8b5cf6;
      --bg-1: #0f172a;
      --bg-2: #1e1b4b;
      --surface: rgba(255, 255, 255, 0.05);
      --surface-border: rgba(255, 255, 255, 0.1);
      --surface-hover: rgba(255, 255, 255, 0.08);
      
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.15);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.15);
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.15);
      
      --glass-blur: blur(16px);
      --shadow-lg: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', sans-serif;
      background: linear-gradient(135deg, var(--bg-1), var(--bg-2));
      background-attachment: fixed;
      color: var(--text-main);
      min-height: 100vh;
      overflow-x: hidden;
    }

    body::before {
      content: ''; position: fixed; top: -50%; left: -50%; width: 200%; height: 200%;
      background: radial-gradient(circle at 40% 60%, rgba(99, 102, 241, 0.12), transparent 40%),
                  radial-gradient(circle at 70% 30%, rgba(139, 92, 246, 0.12), transparent 30%);
      animation: drift 25s infinite alternate ease-in-out; z-index: -1;
    }

    @keyframes drift {
      0% { transform: rotate(0deg) scale(1); }
      100% { transform: rotate(180deg) scale(1.1); }
    }

    .auth-box, .table-wrap, .form-card, .insight-card, .stat-card {
      background: var(--surface); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
      border: 1px solid var(--surface-border); border-radius: 16px; box-shadow: var(--shadow-lg);
    }

    #auth-screen { display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
    .auth-box { width: 100%; max-width: 420px; padding: 40px; }
    .auth-box h1 { text-align: center; margin-bottom: 8px; font-size: 32px; font-weight: 700; background: linear-gradient(135deg, #a5b4fc, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .auth-box .subtitle { text-align: center; color: var(--text-muted); margin-bottom: 32px; font-size: 15px; }

    .auth-tabs { display: flex; margin-bottom: 24px; border-bottom: 1px solid var(--surface-border); }
    .auth-tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: var(--text-muted); font-weight: 600; font-size: 14px; border-bottom: 2px solid transparent; transition: all 0.3s; margin-bottom: -1px; }
    .auth-tab:hover { color: var(--text-main); }
    .auth-tab.active { color: var(--primary); border-bottom-color: var(--primary); }

    .auth-form { display: none; animation: popIn 0.4s ease forwards; }
    .auth-form.active { display: block; }
    @keyframes popIn { from { opacity: 0; transform: translateY(10px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }

    .form-group { margin-bottom: 20px; }
    .form-group label, .form-card label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 8px; }

    input, select, textarea { width: 100%; padding: 12px 16px; background: rgba(0, 0, 0, 0.2); border: 1px solid var(--surface-border); border-radius: 10px; font-size: 15px; color: var(--text-main); transition: all 0.3s ease; font-family: inherit; }
    input::placeholder, textarea::placeholder { color: rgba(255, 255, 255, 0.3); }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2); background: rgba(0, 0, 0, 0.3); }

    .btn-primary { width: 100%; padding: 14px; background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.3s; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }
    .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4); }

    .auth-msg, #form-msg { margin-top: 16px; padding: 12px; border-radius: 10px; font-size: 14px; text-align: center; display: none; animation: popIn 0.3s ease; background: var(--surface); border: 1px solid var(--surface-border); }
    .auth-msg.error { background: var(--danger-bg); color: #fca5a5; border-color: rgba(239, 68, 68, 0.3); display: block; }
    .auth-msg.success { background: var(--success-bg); color: #86efac; border-color: rgba(16, 185, 129, 0.3); display: block; }
    
    #app { display: none; max-width: 1200px; margin: 0 auto; padding-bottom: 40px; }
    nav { background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid var(--surface-border); padding: 0 32px; display: flex; align-items: center; justify-content: space-between; height: 70px; position: sticky; top: 0; z-index: 100; margin-bottom: 32px; border-radius: 0 0 20px 20px; }
    .nav-brand { font-size: 22px; font-weight: 700; background: linear-gradient(135deg, #a5b4fc, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .nav-links { display: flex; gap: 8px; }
    .nav-btn { padding: 10px 18px; border-radius: 8px; cursor: pointer; border: none; font-size: 14px; font-weight: 500; background: transparent; color: var(--text-muted); transition: all 0.3s; font-family: inherit; }
    .nav-btn:hover { background: var(--surface-hover); color: var(--text-main); }
    .nav-btn.active { background: rgba(99, 102, 241, 0.15); color: #a5b4fc; box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.3); }

    .nav-user { font-size: 14px; color: var(--text-muted); display: flex; align-items: center; gap: 16px; }
    .btn-logout { padding: 8px 16px; background: var(--danger-bg); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.3s; font-family: inherit; }
    .btn-logout:hover { background: #ef4444; color: white; }

    .page { display: none; padding: 0 32px; }
    .page.active { display: block; animation: popIn 0.4s ease forwards; }

    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
    .page-header h2 { font-size: 28px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 12px; }

    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; margin-bottom: 32px; }
    .stat-card { padding: 24px; transition: transform 0.3s, box-shadow 0.3s; }
    .stat-card:hover { transform: translateY(-5px); box-shadow: 0 15px 30px -5px rgba(0, 0, 0, 0.4); }
    .stat-card .label { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; margin-bottom: 12px; }
    .stat-card .value { font-size: 36px; font-weight: 800; color: var(--text-main); line-height: 1; }
    .stat-card.red { border-top: 3px solid var(--danger); }
    .stat-card.yellow { border-top: 3px solid var(--warning); }
    .stat-card.green { border-top: 3px solid var(--success); }

    #dashboard-alerts { display: flex; flex-direction: column; gap: 12px; }
    .alert-banner { padding: 16px 20px; border-radius: 12px; font-size: 15px; font-weight: 500; display: flex; align-items: center; animation: popIn 0.4s ease; }
    .alert-banner.red { background: var(--danger-bg); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }
    .alert-banner.yellow { background: var(--warning-bg); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.3); }

    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 800px; }
    th { background: rgba(0, 0, 0, 0.2); padding: 16px 20px; text-align: left; font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; border-bottom: 1px solid var(--surface-border); }
    td { padding: 16px 20px; font-size: 15px; color: var(--text-main); border-bottom: 1px solid var(--surface-border); vertical-align: middle; transition: background 0.2s; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--surface-hover); }

    .badge { display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; }
    .badge.ok { background: var(--success-bg); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge.low { background: var(--warning-bg); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge.out { background: var(--danger-bg); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }

    .btn-sm { padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; font-family: inherit; }
    .btn-edit { background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.3); }
    .btn-edit:hover { background: rgba(99, 102, 241, 0.25); }
    .btn-delete { background: var(--danger-bg); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); margin-left: 6px; }
    .btn-delete:hover { background: rgba(239, 68, 68, 0.25); }

    .btn-action { padding: 10px 20px; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.3s; font-family: inherit; display: inline-flex; align-items: center; gap: 8px; }
    .btn-add { background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }
    .btn-add:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4); }
    .btn-export { background: var(--surface); color: var(--text-main); border: 1px solid var(--surface-border); margin-left: 12px; }
    .btn-export:hover { background: var(--surface-hover); border-color: rgba(255, 255, 255, 0.2); }

    .form-card { max-width: 700px; padding: 32px; margin: 0 auto; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .form-grid .full { grid-column: 1 / -1; }
    
    .form-actions { display: flex; gap: 12px; margin-top: 32px; }
    .btn-save { padding: 12px 28px; background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.3s; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }
    .btn-save:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4); }
    .btn-cancel { padding: 12px 28px; background: transparent; color: var(--text-muted); border: 1px solid var(--surface-border); border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.3s; }
    .btn-cancel:hover { background: var(--surface-hover); color: var(--text-main); border-color: rgba(255, 255, 255, 0.2); }
    #form-msg { display: block; border: none; background: transparent; text-align: left; padding: 0; }

    .insights-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
    .insight-card { padding: 24px; }
    .insight-card h3 { font-size: 18px; color: var(--text-main); margin-bottom: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--surface-border); padding-bottom: 12px; }
    .insight-item { padding: 12px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-size: 14px; color: #cbd5e1; display: flex; align-items: center; gap: 8px; }
    .insight-item:last-child { border-bottom: none; }

    .btn-refresh { padding: 10px 20px; background: linear-gradient(135deg, var(--success), #059669); color: white; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.3s; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); display: flex; align-items: center; gap: 8px; }
    .btn-refresh:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4); }
    .loading { color: var(--text-muted); font-style: italic; text-align: center; padding: 40px; font-size: 15px; }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.1); }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.2); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.3); }
  </style>
"""

# Find head boundaries
start = html.find('<head>') + 6
end = html.find('</head>')

new_html = html[:start] + new_head + html[end:]

with codecs.open('c:\\InventoryIQ\\index.html', 'w', 'utf-8') as f:
    f.write(new_html)

print("CSS replaced successfully!")

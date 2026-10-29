"""User-facing backend email/SNS text says Panindo, not InventoryIQ (table names stay)."""
from pathlib import Path

LAMBDA = Path(__file__).resolve().parents[3] / 'lambda'
RENAMED = {
    'Authentication.mjs': ['InventoryIQ — Password Reset', 'your InventoryIQ account'],
    'OrgInvites.py': ['invited to InventoryIQ', 'inventory on InventoryIQ'],
    'LowItemInsight.py': ['InventoryIQ Stock Alert', 'InventoryIQ — Stock Alert'],
    'DailyAlert.py': ['report from InventoryIQ', 'InventoryIQ Daily Report'],
    'BarcodeLookup.py': ["'User-Agent': 'InventoryIQ/1.0'"],
}


def test_user_facing_strings_say_panindo():
    for name, old_phrases in RENAMED.items():
        text = (LAMBDA / name).read_text()
        for old in old_phrases:
            assert old not in text, f'{name}: {old}'
            assert old.replace('InventoryIQ', 'Panindo') in text, f'{name}: {old}'


def test_daily_report_banner_says_panindo_and_stays_aligned():
    lines = (LAMBDA / 'DailyAlert.py').read_text().splitlines()
    top = next(i for i, line in enumerate(lines) if '╔' in line)
    box = [line.strip().strip('",') for line in lines[top:top + 3]]
    assert 'PANINDO — DAILY STOCK REPORT' in box[1] and 'INVENTORYIQ' not in box[1]
    assert len({len(line) for line in box}) == 1

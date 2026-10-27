"""User-facing backend email/SNS text says Panindo, not InventoryIQ (table names stay)."""
from pathlib import Path

LAMBDA = Path(__file__).resolve().parents[3] / 'lambda'
RENAMED = {
    'Authentication.mjs': ['InventoryIQ — Password Reset', 'your InventoryIQ account'],
    'OrgInvites.py': ['invited to InventoryIQ', 'inventory on InventoryIQ'],
    'LowItemInsight.py': ['InventoryIQ Stock Alert'],
    'DailyAlert.py': ['report from InventoryIQ'],
}


def test_user_facing_strings_say_panindo():
    for name, old_phrases in RENAMED.items():
        text = (LAMBDA / name).read_text()
        for old in old_phrases:
            assert old not in text, f'{name}: {old}'
            assert old.replace('InventoryIQ', 'Panindo') in text, f'{name}: {old}'

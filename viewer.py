"""Compatibility entry point for older Screen Time desktop shortcuts."""
from kids_policy.ui_client import send

if __name__ == '__main__':
    send({'op': 'dashboard'})

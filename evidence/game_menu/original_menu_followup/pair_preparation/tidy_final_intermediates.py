"""Exact final five-object/environment cleanup; requires root's separate action."""
from file_only_reuse import STAGE, PROJECT, load


def main():
    module = load('tools/tidy_menu_suite_intermediates.py',
        '5d9335cbc62f2d18710ec85ae493461dd87a0badd62835908fb448ba5a0dd4ca',
        '_original_menu_final_intermediates')
    if module.audit.PROJECT != PROJECT:raise RuntimeError('Unexpected reused cleanup project')
    module.audit.STAGE = STAGE.parent
    module.main()


if __name__ == '__main__':main()

"""Keep retained production backdrop source gates typed and fail closed."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_interactive_decisions import verify_popup_backdrop_source


LEGACY = r'''
if(!uiFrame.cityBackdrop.empty()){
    png=backdropFolder+L"\\city-backdrop.png";
}
live.VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop);
'''
TYPED = r'''
if(!uiFrame.cityBackdrop.empty() && !uiFrame.economicBackdrop.empty())
    throw std::logic_error("A production scene cannot retain both city and economic backdrops");
const bool economicBackdrop=!uiFrame.economicBackdrop.empty();
if(!uiFrame.cityBackdrop.empty() || economicBackdrop){
    Write(backdropSnapshot,economicBackdrop?uiFrame.economicBackdrop:uiFrame.cityBackdrop);
    std::printf("request",economicBackdrop?"economic-overview":"city-view");
    WaitForUiPacket(window,backdropRevision,closeRequested,error);
    if(!LoadScenePacket(backdropFolder+L"\\scene.packet",&backdrop,&error) || backdrop.width!=1920 || backdrop.height!=1080)
        throw std::runtime_error("invalid packet");
    backdrop.hits.clear();backdrop.scrolls.clear();
    window.OverlayPreparedGpuFrame(backdrop,&error);
    png=backdropFolder+(economicBackdrop?L"\\economic-backdrop.png":L"\\city-backdrop.png");
}
live.VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop,uiFrame.economicBackdrop);
'''


class PopupBackdropSourceContract(unittest.TestCase):
    def test_original_city_and_typed_city_economic_are_distinct(self):
        self.assertEqual(verify_popup_backdrop_source(LEGACY), "CITY_ONLY")
        self.assertEqual(verify_popup_backdrop_source(TYPED), "TYPED_CITY_OR_ECONOMIC")

    def test_missing_type_routing_validation_or_input_isolation_is_rejected(self):
        mutations = (
            (' && !uiFrame.economicBackdrop.empty()', ''),
            ('throw std::logic_error', 'report_error'),
            ('const bool economicBackdrop=', 'const bool inventedBackdrop='),
            (' || economicBackdrop)', ')'),
            ('Write(backdropSnapshot,economicBackdrop?uiFrame.economicBackdrop:uiFrame.cityBackdrop)',
             'Write(backdropSnapshot,uiFrame.cityBackdrop)'),
            ('"economic-overview":"city-view"', '"city-view":"economic-overview"'),
            ('WaitForUiPacket(window,backdropRevision,closeRequested,error)', ''),
            ('backdrop.width!=1920', 'backdrop.width!=1280'),
            ('backdrop.height!=1080', 'backdrop.height!=720'),
            ('backdrop.hits.clear();backdrop.scrolls.clear();', ''),
            ('window.OverlayPreparedGpuFrame(backdrop,&error)', ''),
            ('economic-backdrop.png', 'city-backdrop.png'),
            ('VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop,uiFrame.economicBackdrop)',
             'VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop)'),
        )
        for old, new in mutations:
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                verify_popup_backdrop_source(TYPED.replace(old, new))

    def test_partial_typed_branch_cannot_fall_back_to_legacy_tokens(self):
        with self.assertRaises(RuntimeError):
            verify_popup_backdrop_source(LEGACY + '\nuiFrame.economicBackdrop;')
        with self.assertRaises(RuntimeError):
            verify_popup_backdrop_source(LEGACY + TYPED.replace('economic-backdrop.png', 'invalid.png'))

    def test_legacy_missing_snapshot_validation_or_original_path_is_rejected(self):
        for token in ('if(!uiFrame.cityBackdrop.empty())', 'city-backdrop.png',
                      'VerifyUiSnapshot(uiFrame.snapshot,uiFrame.cityBackdrop)'):
            with self.subTest(token=token), self.assertRaises(RuntimeError):
                verify_popup_backdrop_source(LEGACY.replace(token, ''))


if __name__ == "__main__":
    unittest.main()

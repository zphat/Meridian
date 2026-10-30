"""Regression: an outdated background Meridian must not be reused during upgrade."""
import io
import json
import unittest
from unittest.mock import patch
import argparse
import meridian

class FakeResponse:
    def __init__(self, version):
        self.payload=io.BytesIO(json.dumps({"app":"Meridian","version":version}).encode())
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,*args,**kwargs): return self.payload.read(*args,**kwargs)

class UpgradeTests(unittest.TestCase):
    def test_old_version_is_rejected(self):
        class OccupiedServer:
            def __init__(self,*args): raise OSError("Address already in use")
        args=argparse.Namespace(port=8765,no_browser=True,offline=True,no_tray=True,
                                 data_dir="/unused",browser_tab=False)
        with patch.object(meridian,"ThreadingHTTPServer",OccupiedServer), patch.object(
            meridian.urllib.request,"urlopen",return_value=FakeResponse("0.2.7")
        ):
            with self.assertRaisesRegex(RuntimeError,"older Meridian instance"):
                meridian.serve(args)
    def test_same_version_is_reused(self):
        class OccupiedServer:
            def __init__(self,*args): raise OSError("Address already in use")
        args=argparse.Namespace(port=8765,no_browser=True,offline=True,no_tray=True,
                                 data_dir="/unused",browser_tab=False)
        with patch.object(meridian,"ThreadingHTTPServer",OccupiedServer), patch.object(
            meridian.urllib.request,"urlopen",return_value=FakeResponse(meridian.VERSION)
        ):
            self.assertIsNone(meridian.serve(args))

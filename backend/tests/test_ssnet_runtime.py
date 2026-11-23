"""Verify that cancelling a job really terminates its owned subprocess."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ssnet


class LifetimeTests(unittest.TestCase):
    def test_cancellation_terminates_worker_process(self):
        with tempfile.TemporaryDirectory(prefix='ssnet-lifetime-') as temporary:
            root=Path(temporary)
            script=root/'services'/'ssnet'/'worker.py'
            script.parent.mkdir(parents=True)
            script.write_text('import time\nwhile True: time.sleep(.1)\n',encoding='utf-8')
            processes=[]
            original=ssnet.subprocess.Popen
            def spawn(*args,**kwargs):
                process=original(*args,**kwargs)
                processes.append(process)
                return process
            cancel=threading.Event()
            results=[]
            with patch.object(ssnet,'ROOT',root),patch.object(ssnet,'PYTHON',Path(sys.executable)),patch.object(ssnet.subprocess,'Popen',side_effect=spawn):
                thread=threading.Thread(target=lambda:results.append(ssnet.execute_local(root/'job',{},lambda _:None,cancel)))
                thread.start()
                try:
                    for _ in range(100):
                        if processes:
                            break
                        time.sleep(.02)
                    self.assertTrue(processes)
                    self.assertIsNone(processes[0].poll())
                finally:
                    cancel.set()
                    thread.join(8)
                self.assertFalse(thread.is_alive())
                self.assertIsNotNone(processes[0].poll())
                self.assertEqual(results,[None])


if __name__=='__main__':
    unittest.main()

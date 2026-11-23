"""PeakNet worker entry point; heavy model imports happen after the first request."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_worker import serve

configuration = json.loads(os.environ['RAMANCLOUD_INFERENCE_CONFIG'])
processor = None


def predict(payload):
    global processor
    if processor is None:
        from predictor import PeakNetPredictor
        processor = PeakNetPredictor(configuration['profile'], configuration['paths'])
    return processor.run(payload)


if __name__ == '__main__':
    serve('ramancloud-peaknet', configuration['profile']['id'], predict)

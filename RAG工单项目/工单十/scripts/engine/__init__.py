import os
import sys

# 在任何 import 之前设置 torch 路径到 PATH
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.join(_current_dir, '..', '..')
_torch_lib_path = os.path.abspath(os.path.join(_project_root, '.venv', 'lib', 'site-packages', 'torch', 'lib'))
if os.path.exists(_torch_lib_path):
    os.environ['PATH'] = _torch_lib_path + ';' + os.environ.get('PATH', '')

from scripts.engine.base import BaseEngine
from scripts.engine.mineru_engine import MinerUEngine
from scripts.engine.paddleocr_engine import PaddleOCREngine

__all__ = ["BaseEngine", "MinerUEngine", "PaddleOCREngine"]

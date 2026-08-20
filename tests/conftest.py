"""테스트 공통 설정.

프로젝트 루트를 import 경로에 넣고, 소스를 읽는 검사들이
어느 디렉터리에서 pytest 를 돌려도 같은 파일을 보게 한다.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

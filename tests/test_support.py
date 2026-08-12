"""테스트 실행 공통 헬퍼. 이 프로젝트는 pytest를 쓰지 않고 자체 러너를 쓴다."""


def run_test_classes(*classes) -> bool:
    passed = 0
    failed = 0
    for cls in classes:
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    passed += 1
                    print(f"  PASS: {cls.__name__}.{method_name}")
                except AssertionError as e:
                    failed += 1
                    print(f"  FAIL: {cls.__name__}.{method_name} - {e}")
                except Exception as e:
                    failed += 1
                    print(f"  ERROR: {cls.__name__}.{method_name} - {e}")
    print(f"\n결과: {passed} passed, {failed} failed")
    return failed == 0

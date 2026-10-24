import sys
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--smoke-test" in sys.argv:
        index = sys.argv.index("--smoke-test")
        report = sys.argv[index + 1]
        sys.argv = sys.argv[:1]
        from jparty.selftest import run
        sys.exit(run(report))
    if "--buzzers" in sys.argv:
        from physicalbuzzers.physicalbuzzers import run_buzzers
        run_buzzers()
        sys.exit(0)

    from jparty.main import main
    main()
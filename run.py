import sys

if __name__ == "__main__":
    if "--buzzers" in sys.argv:
        from physicalbuzzers.physicalbuzzers import run_buzzers
        run_buzzers()
        sys.exit(0)

    from jparty.main import main
    main()
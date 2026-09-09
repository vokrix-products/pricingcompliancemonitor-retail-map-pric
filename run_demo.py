from processor import process_file


def main():
    test_bytes = b"supplier,product,price\nAcme,Widget,9.99"
    results = process_file(test_bytes)

    assert isinstance(results, list), "process_file must return a list"

    for record in results:
        print(f"{record['title']} -> {record['status']}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

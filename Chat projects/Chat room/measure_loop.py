import time


def main():
    iterations = 1_000_000
    total = 0

    start = time.perf_counter()

    for number in range(iterations):
        total += number

    elapsed = time.perf_counter() - start

    print(f"Loop completed {iterations:,} iterations in {elapsed:.6f} seconds.")
    print(f"Result: {total}")


if __name__ == "__main__":
    main()
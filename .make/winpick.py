def pick(options, title, multiselect=False, **kwargs):
    """Jednoduchá náhrada za pick bez závislosti na curses"""
    print("\n" + title)
    for i, option in enumerate(options, 1):
        print(f"{i}) {option}")

    if not multiselect:
        while True:
            try:
                choice = input("\nEnter the number of your choice: ")
                index = int(choice) - 1
                if 0 <= index < len(options):
                    return options[index], index
                print(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                print("Please enter a valid number")
    else:
        print("Enter numbers separated by spaces (e.g. 1 3) or press Enter for an empty selection:")
        while True:
            try:
                line = input("\nEnter the numbers of your choice: ").strip()
                if not line:
                    return []
                indices = [int(c) - 1 for c in line.replace(',', ' ').split()]
                if all(0 <= i < len(options) for i in indices):
                    return [(options[i], i) for i in indices]
                print(f"Please enter numbers between 1 and {len(options)}")
            except ValueError:
                print("Please enter valid numbers")

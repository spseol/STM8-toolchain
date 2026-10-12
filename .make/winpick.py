def pick(options, title, multiselect=False, **kwargs):
    """Jednoduchá náhrada za pick bez závislosti na curses"""
    print("\n" + title)
    for i, option in enumerate(options, 1):
        print(f"{i}) {option}")

    if not multiselect:
        while True:
            try:
                choice = input("\nZadejte číslo volby: ")
                index = int(choice) - 1
                if 0 <= index < len(options):
                    return options[index], index
                print(f"Prosím zadejte číslo mezi 1 a {len(options)}")
            except ValueError:
                print("Prosím zadejte platné číslo")
    else:
        print("Zadejte čísla oddělená mezerou (např. 1 3) nebo Enter pro prázdný výběr:")
        while True:
            try:
                line = input("\nZadejte čísla volby: ").strip()
                if not line:
                    return []
                indices = [int(c) - 1 for c in line.replace(',', ' ').split()]
                if all(0 <= i < len(options) for i in indices):
                    return [(options[i], i) for i in indices]
                print(f"Prosím zadejte čísla mezi 1 a {len(options)}")
            except ValueError:
                print("Prosím zadejte platná čísla")

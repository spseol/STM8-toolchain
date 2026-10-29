import json
import os
import sys

URL = "https://www.st.com/resource/en/datasheet/{device}.pdf"

# build descriptions per family; the Makefile includes ../SPLSPL/mk/$(DEVICE).mk
MK_DIR = "../SPLSPL/mk"

DEVICES = {
    "Value line (00X)": {
        "STM8S003F3": "stm8s003f3",
        "STM8S003K3": "stm8s003f3",
        "STM8S005C6": "stm8s005c6",
        "STM8S005K6": "stm8s005c6",
        "STM8S007C8": "stm8s007c8",
    },
    "Access line (103/105/903)": {
        "STM8S103F2": "stm8s103f2",
        "STM8S103F3": "stm8s103f2",
        "STM8S103K3": "stm8s103f2",
        "STM8S103C4": "stm8s105c4",
        "STM8S103C6": "stm8s105c4",
        "STM8S103K4": "stm8s105c4",
        "STM8S103K6": "stm8s105c4",
        "STM8S103S4": "stm8s105c4",
        "STM8S103S6": "stm8s105c4",
        "STM8S105C4": "stm8s105c4",
        "STM8S105C6": "stm8s105c4",
        "STM8S105K4": "stm8s105c4",
        "STM8S105K6": "stm8s105c4",
        "STM8S105S4": "stm8s105c4",
        "STM8S105S6": "stm8s105c4",
        "STM8S903F3": "stm8s903k3",
        "STM8S903K3": "stm8s903k3",
    },
    "Performance line (207/208)": {
        "STM8S207C6": "stm8s207mb",
        "STM8S207C8": "stm8s207mb",
        "STM8S207CB": "stm8s207mb",
        "STM8S207K6": "stm8s207mb",
        "STM8S207K8": "stm8s207mb",
        "STM8S207M8": "stm8s207mb",
        "STM8S207MB": "stm8s207mb",
        "STM8S207R6": "stm8s207mb",
        "STM8S207R8": "stm8s207mb",
        "STM8S207RB": "stm8s207mb",
        "STM8S207S6": "stm8s207mb",
        "STM8S207S8": "stm8s207mb",
        "STM8S207SB": "stm8s207mb",
        "STM8S208C6": "stm8s207mb",
        "STM8S208C8": "stm8s207mb",
        "STM8S208CB": "stm8s207mb",
        "STM8S208MB": "stm8s207mb",
        "STM8S208R8": "stm8s207mb",
        "STM8S208RB": "stm8s207mb",
        "STM8S208S6": "stm8s207mb",
    },
}

datasheets = {}
for familly in DEVICES:
    for device in DEVICES[familly]:
        datasheets[device] = URL.format(device=DEVICES[familly][device])



def supported(chip, mk_dir=MK_DIR):
    """Can the SPL build the family of CHIP? The Makefile's DEVICE is its first 8 characters."""
    return os.path.isfile(os.path.join(mk_dir, chip.upper()[:8] + ".mk"))


def available(devices=DEVICES, mk_dir=MK_DIR):
    """DEVICES without the chips the SPL cannot build; all of them while the SPL is not downloaded."""
    if not os.path.isdir(mk_dir):
        return devices
    result = {}
    for family, chips in devices.items():
        kept = {chip: sheet for chip, sheet in chips.items() if supported(chip, mk_dir)}
        if kept:
            result[family] = kept
    return result


def check(chip, devices=DEVICES, mk_dir=MK_DIR):
    """CHIP in lower case when it can be selected, otherwise ValueError with the reason."""
    name = chip.upper()
    if not any(name in chips for chips in devices.values()):
        raise ValueError(f"Unknown chip: {chip}")
    if os.path.isdir(mk_dir) and not supported(name, mk_dir):
        raise ValueError(f"SPL has no support for {name[:8]}")
    return name.lower()


if __name__ == "__main__":
    # devices.py             selectable chips as JSON (for the VS Code extension)
    # devices.py --check X   print X in lower case, or the reason it cannot be selected
    if sys.argv[1:2] == ["--check"]:
        try:
            print(check(sys.argv[2]))
        except IndexError:
            sys.exit("usage: devices.py [--check CHIP]")
        except ValueError as error:
            sys.exit(str(error))
    else:
        print(json.dumps(available()))

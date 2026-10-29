import pytest

from conftest import gdb_batch, json_lines, run_make


@pytest.fixture(scope="module", autouse=True)
def built():
    proc = run_make(["debug-files"])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def periph(model, name):
    return next(p for p in model["periphs"] if p["name"] == name)


def reg(p, name):
    return next(r for r in p["regs"] if r["name"] == name)


# --- without a chip ------------------------------------------------------------------------


def test_static_lists_all_periphs():
    (model,) = json_lines(gdb_batch(["sfr-json"]))
    assert model["running"] is False
    tim4 = periph(model, "TIM4")
    assert tim4["base"] == 0x5340
    assert any(b["name"] == "CEN" and b["mask"] == 1 for b in reg(tim4, "CR1")["bits"])
    assert reg(periph(model, "UART1"), "DR")["sideEffect"] is True
    assert all(r["value"] is None and r["prev"] is None for p in model["periphs"] for r in p["regs"])


def test_unknown_periph_errors():
    proc = gdb_batch(["sfr-json NOPE"])
    assert "NOPE" in proc.stderr
    assert json_lines(proc) == []


def test_merge_field():
    proc = gdb_batch(["python print(merge_field(0x01, 0x08, 1), merge_field(0xFF, 0x70, 0x2))"])
    assert proc.stdout.split() == ["9", "175"]  # 0x09, 0xAF


def test_set_rejects_oversized_field():
    proc = gdb_batch(["sfr-set SPI.CR1.BR 9"])
    assert "Value 9 does not fit field SPI.CR1.BR (3 bits)" in proc.stderr


def test_set_rejects_oversized_register():
    proc = gdb_batch(["sfr-set TIM4.ARR 256"])
    assert "Value 256 does not fit register TIM4.ARR (8 bits)" in proc.stderr


def test_set_field_of_a_side_effect_register_is_refused():
    """A field write reads the register first, and that read clears flags (AWU.CSR.AWUF)."""
    proc = gdb_batch(["sfr-set AWU.CSR.AWUEN 1"])
    assert "AWU.CSR cannot be changed field by field" in proc.stderr
    assert "sfr-set AWU.CSR VALUE" in proc.stderr


def test_gpio_registers_have_pin_fields():
    """stm8s.h has no per-bit macros for the GPIO registers: PIN0..PIN7 are made up."""
    (model,) = json_lines(gdb_batch(["sfr-json"]))
    gpioa = periph(model, "GPIOA")
    for name in ("ODR", "IDR", "DDR", "CR1", "CR2"):
        bits = reg(gpioa, name)["bits"]
        assert sorted((b["name"], b["mask"]) for b in bits) == sorted((f"PIN{n}", 1 << n) for n in range(8)), name
    assert {b["desc"] for b in reg(gpioa, "ODR")["bits"]} == {f"pin {n}" for n in range(8)}


def test_gpio_idr_is_read_only():
    (model,) = json_lines(gdb_batch(["sfr-json"]))
    gpioa = periph(model, "GPIOA")
    assert reg(gpioa, "IDR")["readOnly"] is True
    assert reg(gpioa, "ODR")["readOnly"] is False
    assert reg(periph(model, "TIM4"), "CR1")["readOnly"] is False
    assert "GPIOA.IDR is read-only" in gdb_batch(["sfr-set GPIOA.IDR 1"]).stderr
    assert "GPIOA.IDR is read-only" in gdb_batch(["sfr-set GPIOA.IDR.PIN0 1"]).stderr


# --- on the chip ---------------------------------------------------------------------------


@pytest.mark.hw
def test_values_on_chip():
    tim4, uart1 = json_lines(gdb_batch(["sfr-json TIM4", "sfr-json UART1"], hw=True))
    assert isinstance(reg(periph(tim4, "TIM4"), "CR1")["value"], int)
    assert reg(periph(uart1, "UART1"), "DR")["value"] is None
    assert isinstance(reg(periph(uart1, "UART1"), "SR")["value"], int)


@pytest.mark.hw
def test_explicit_read_of_side_effect_reg():
    (uart1,) = json_lines(gdb_batch(["sfr-json UART1.DR"], hw=True))
    assert isinstance(reg(periph(uart1, "UART1"), "DR")["value"], int)


@pytest.mark.hw
def test_set_roundtrip():
    proc = gdb_batch(["sfr-set TIM4.ARR 0x55", "sfr-json TIM4.ARR",
                      "sfr-set TIM4.CR1.ARPE 1", "sfr-json TIM4.CR1"], hw=True)
    arr, cr1 = json_lines(proc)
    assert reg(periph(arr, "TIM4"), "ARR")["value"] == 0x55
    assert reg(periph(cr1, "TIM4"), "CR1")["value"] & 0x80


@pytest.mark.hw
def test_gpio_pin_write():
    proc = gdb_batch(["sfr-set GPIOD.ODR.PIN7 1", "sfr-json GPIOD.ODR"], hw=True)
    (gpiod,) = json_lines(proc)
    assert reg(periph(gpiod, "GPIOD"), "ODR")["value"] & 0x80  # GPIOA latches nothing on this board


@pytest.mark.hw
def test_running_errors():
    proc = gdb_batch(["continue&", "sfr-json TIM4", "sfr-set TIM4.ARR 1"], hw=True)
    assert proc.stderr.count("Program is running, pause it first.") == 2

# hatty — MIT License. See LICENSE file for details.
"""KelvinSlider and PercentageSlider are both a Widget(can_focus=True) with a
clamped reactive `value`, identical key handling (arrows/home/end/pageup/
pagedown), and a `Changed` message on every change — one parametrized suite
exercises both instead of two near-identical modules."""

import pytest
from textual.app import App, ComposeResult

from hatty.ui.controls.kelvin_slider import KelvinSlider
from hatty.ui.controls.percentage_slider import PercentageSlider

# (widget class, constructor kwargs, initial/min/max/step/big_step, render suffix)
_KELVIN = pytest.param(
    KelvinSlider,
    {"value": 4000, "min_value": 2000, "max_value": 6500},
    {"initial": 4000, "min": 2000, "max": 6500, "step": 100, "big_step": 500, "suffix": "4000K"},
    id="kelvin",
)
_PERCENTAGE = pytest.param(
    PercentageSlider,
    {"value": 50},
    {"initial": 50, "min": 0, "max": 100, "step": 1, "big_step": 10, "suffix": "50%"},
    id="percentage",
)
SLIDERS = [_KELVIN, _PERCENTAGE]


def _slider_app(widget_cls, kwargs):
    class SliderApp(App):
        def compose(self) -> ComposeResult:
            yield widget_cls(**kwargs, id="slider")

    return SliderApp()


@pytest.mark.parametrize("widget_cls, kwargs, expect", SLIDERS)
async def test_initial_value_focus_and_render(widget_cls, kwargs, expect):
    app = _slider_app(widget_cls, kwargs)
    async with app.run_test() as pilot:
        slider = pilot.app.query_one("#slider", widget_cls)
        assert slider.value == expect["initial"]
        assert slider.can_focus is True
        assert expect["suffix"] in slider.render()


@pytest.mark.parametrize("widget_cls, kwargs, expect", SLIDERS)
async def test_key_navigation_and_clamping(widget_cls, kwargs, expect):
    app = _slider_app(widget_cls, kwargs)
    async with app.run_test() as pilot:
        slider = pilot.app.query_one("#slider", widget_cls)
        slider.focus()
        await pilot.pause()

        # right/left and up/down are equivalent increment/decrement keys.
        await pilot.press("right")
        assert slider.value == expect["initial"] + expect["step"]
        await pilot.press("left")
        assert slider.value == expect["initial"]
        await pilot.press("up")
        assert slider.value == expect["initial"] + expect["step"]
        await pilot.press("down")
        assert slider.value == expect["initial"]

        await pilot.press("pageup")
        assert slider.value == expect["initial"] + expect["big_step"]
        await pilot.press("pagedown")
        assert slider.value == expect["initial"]
        await pilot.press("pagedown")
        assert slider.value == expect["initial"] - expect["big_step"]

        await pilot.press("home")
        assert slider.value == expect["min"]
        await pilot.press("end")
        assert slider.value == expect["max"]

        # Assigning past a bound clamps; incrementing/decrementing at a bound
        # via keys is a no-op rather than overshooting.
        slider.value = expect["max"] + expect["big_step"]
        assert slider.value == expect["max"]
        await pilot.press("right")
        assert slider.value == expect["max"]

        slider.value = expect["min"] - expect["big_step"]
        assert slider.value == expect["min"]
        await pilot.press("left")
        assert slider.value == expect["min"]


@pytest.mark.parametrize("widget_cls, kwargs, expect", SLIDERS)
async def test_changed_message_posted_on_arrow_press(widget_cls, kwargs, expect):
    messages: list[int] = []

    class TrackingApp(App):
        def compose(self) -> ComposeResult:
            yield widget_cls(**kwargs, id="slider")

        def on_kelvin_slider_changed(self, event: KelvinSlider.Changed) -> None:
            messages.append(event.value)

        def on_percentage_slider_changed(self, event: PercentageSlider.Changed) -> None:
            messages.append(event.value)

    async with TrackingApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", widget_cls)
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert messages == [expect["initial"] + expect["step"]]

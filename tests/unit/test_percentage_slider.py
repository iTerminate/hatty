# hatty — MIT License. See LICENSE file for details.
from textual.app import App, ComposeResult

from hatty.ui.controls.percentage_slider import PercentageSlider


class SliderApp(App):
    def compose(self) -> ComposeResult:
        yield PercentageSlider(value=50, id="slider")


async def test_initial_value():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        assert slider.value == 50


async def test_value_clamped_above_max():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.value = 150
        assert slider.value == 100


async def test_value_clamped_below_min():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.value = -10
        assert slider.value == 0


async def test_right_arrow_increments():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        assert slider.value == 51


async def test_left_arrow_decrements():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("left")
        assert slider.value == 49


async def test_up_arrow_increments():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("up")
        assert slider.value == 51


async def test_down_arrow_decrements():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("down")
        assert slider.value == 49


async def test_home_jumps_to_zero():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("home")
        assert slider.value == 0


async def test_end_jumps_to_hundred():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("end")
        assert slider.value == 100


async def test_pageup_increments_by_big_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("pageup")
        assert slider.value == 60


async def test_pagedown_decrements_by_big_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("pagedown")
        assert slider.value == 40


async def test_increment_clamped_at_max():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.value = 100
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        assert slider.value == 100


async def test_decrement_clamped_at_min():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.value = 0
        slider.focus()
        await pilot.pause()
        await pilot.press("left")
        assert slider.value == 0


async def test_render_shows_percentage_text():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        assert "50%" in slider.render()


async def test_can_focus():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        assert slider.can_focus is True


async def test_changed_message_posted_on_arrow_press():
    messages: list[int] = []

    class TrackingApp(App):
        def compose(self) -> ComposeResult:
            yield PercentageSlider(value=50, id="slider")

        def on_percentage_slider_changed(self, event: PercentageSlider.Changed) -> None:
            messages.append(event.value)

    async with TrackingApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", PercentageSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert messages == [51]

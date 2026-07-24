# hatty — MIT License. See LICENSE file for details.
from textual.app import App, ComposeResult

from hatty.ui.controls.kelvin_slider import KelvinSlider


class SliderApp(App):
    def compose(self) -> ComposeResult:
        yield KelvinSlider(value=4000, min_value=2000, max_value=6500, id="slider")


async def test_initial_value():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        assert slider.value == 4000


async def test_value_clamped_above_max():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.value = 9000
        assert slider.value == 6500


async def test_value_clamped_below_min():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.value = 500
        assert slider.value == 2000


async def test_right_arrow_increments_by_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        assert slider.value == 4100


async def test_left_arrow_decrements_by_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("left")
        assert slider.value == 3900


async def test_home_jumps_to_min():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("home")
        assert slider.value == 2000


async def test_end_jumps_to_max():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("end")
        assert slider.value == 6500


async def test_pageup_increments_by_big_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("pageup")
        assert slider.value == 4500


async def test_pagedown_decrements_by_big_step():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("pagedown")
        assert slider.value == 3500


async def test_render_shows_kelvin_text():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        assert "4000K" in slider.render()


async def test_can_focus():
    async with SliderApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        assert slider.can_focus is True


async def test_changed_message_posted_on_arrow_press():
    messages: list[int] = []

    class TrackingApp(App):
        def compose(self) -> ComposeResult:
            yield KelvinSlider(value=4000, min_value=2000, max_value=6500, id="slider")

        def on_kelvin_slider_changed(self, event: KelvinSlider.Changed) -> None:
            messages.append(event.value)

    async with TrackingApp().run_test() as pilot:
        slider = pilot.app.query_one("#slider", KelvinSlider)
        slider.focus()
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert messages == [4100]

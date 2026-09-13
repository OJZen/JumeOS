// SPDX-License-Identifier: GPL-2.0-only
/*
 * MIPI-DSI panel driver for the 1024x768 panel in the R46H handheld.
 *
 * The panel controller marking is not yet known.  The initialization table
 * below is a lossless decoding of the downstream Rockchip 4.4
 * panel-init-sequence: 167 DCS short writes followed by EXIT_SLEEP_MODE and
 * SET_DISPLAY_ON with their original delays.
 */

#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/media-bus-format.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>

#include <drm/drm_connector.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

#include <video/mipi_display.h>

#define R46H_PANEL_POWER_UV		2800000
#define R46H_PANEL_BACKLIGHT_UV	3300000

enum r46h_panel_supply {
	R46H_PANEL_SUPPLY_POWER,
	R46H_PANEL_SUPPLY_BACKLIGHT,
	R46H_PANEL_NUM_SUPPLIES,
};

struct r46h_panel {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct gpio_desc *reset_gpio;
	struct regulator_bulk_data supplies[R46H_PANEL_NUM_SUPPLIES];
	bool supply_enabled[R46H_PANEL_NUM_SUPPLIES];
	bool handoff_pending;
	bool handoff_active;
	bool handoff_used;
	bool initialized;
};

struct r46h_panel_handoff_state {
	int reset_direction;
	int reset_raw;
	int power_enabled;
	int backlight_enabled;
	int power_uv;
	int backlight_uv;
};

struct r46h_panel_command {
	u8 command;
	u8 value;
};

static const struct r46h_panel_command r46h_panel_init_commands[] = {
	{ 0xee, 0x01 }, { 0xea, 0x07 }, { 0xeb, 0x12 }, { 0x0a, 0x8b },
	{ 0x17, 0x35 }, { 0x1d, 0x33 }, { 0x21, 0x01 }, { 0x28, 0x1c },
	{ 0x29, 0x27 }, { 0x2a, 0x63 }, { 0x2b, 0xb5 }, { 0x2c, 0x00 },
	{ 0x2d, 0x33 }, { 0x2f, 0xf3 }, { 0xee, 0x02 }, { 0x39, 0x78 },
	{ 0x39, 0x78 }, { 0x00, 0x00 }, { 0x01, 0x18 }, { 0x02, 0x15 },
	{ 0x03, 0x10 }, { 0x04, 0x18 }, { 0x05, 0x3f }, { 0x06, 0x11 },
	{ 0x07, 0x11 }, { 0x08, 0x11 }, { 0x09, 0x0f }, { 0x0a, 0x10 },
	{ 0x0b, 0x54 }, { 0x0c, 0x14 }, { 0x0d, 0x17 }, { 0x0e, 0x35 },
	{ 0x0f, 0x37 }, { 0x10, 0x3f }, { 0x20, 0x00 }, { 0x21, 0x18 },
	{ 0x22, 0x15 }, { 0x23, 0x10 }, { 0x24, 0x12 }, { 0x25, 0x37 },
	{ 0x26, 0x0b }, { 0x27, 0x0d }, { 0x28, 0x0d }, { 0x29, 0x0b },
	{ 0x2a, 0x10 }, { 0x2b, 0x54 }, { 0x2c, 0x14 }, { 0x2d, 0x17 },
	{ 0x2e, 0x35 }, { 0x2f, 0x37 }, { 0x30, 0x3f }, { 0xee, 0x04 },
	{ 0x00, 0x04 }, { 0x01, 0x01 }, { 0x02, 0x80 }, { 0x03, 0x04 },
	{ 0x04, 0x00 }, { 0x06, 0x16 }, { 0x07, 0x03 }, { 0x08, 0x13 },
	{ 0x09, 0x0a }, { 0x0a, 0x0f }, { 0x0b, 0x10 }, { 0x22, 0x80 },
	{ 0x24, 0x08 }, { 0x2a, 0x00 }, { 0xee, 0x05 }, { 0x00, 0x04 },
	{ 0x01, 0x08 }, { 0x02, 0x55 }, { 0x03, 0x05 }, { 0x04, 0x00 },
	{ 0x05, 0x04 }, { 0x06, 0x00 }, { 0x07, 0x13 }, { 0x08, 0x1e },
	{ 0x09, 0x66 }, { 0x0d, 0x22 }, { 0x10, 0x08 }, { 0x11, 0x0c },
	{ 0x12, 0x55 }, { 0x13, 0x05 }, { 0x19, 0x14 }, { 0x1a, 0x76 },
	{ 0x23, 0x00 }, { 0x43, 0x13 }, { 0x40, 0x44 }, { 0x41, 0x00 },
	{ 0x30, 0x01 }, { 0x31, 0x01 }, { 0x32, 0x00 }, { 0x33, 0x14 },
	{ 0x34, 0x14 }, { 0x35, 0xb4 }, { 0x36, 0x01 }, { 0x37, 0x01 },
	{ 0x38, 0x00 }, { 0x39, 0x14 }, { 0x3a, 0x14 }, { 0x44, 0x01 },
	{ 0x45, 0x81 }, { 0x46, 0x05 }, { 0xee, 0x06 }, { 0x00, 0x23 },
	{ 0x01, 0x01 }, { 0x02, 0x04 }, { 0x06, 0xcd }, { 0x08, 0x67 },
	{ 0x09, 0x45 }, { 0x0a, 0x23 }, { 0x0b, 0x01 }, { 0xee, 0x07 },
	{ 0x00, 0x3c }, { 0x01, 0x20 }, { 0x02, 0x20 }, { 0x03, 0x21 },
	{ 0x04, 0x21 }, { 0x05, 0x3c }, { 0x06, 0x3c }, { 0x07, 0x04 },
	{ 0x08, 0x04 }, { 0x09, 0x0c }, { 0x0a, 0x0c }, { 0x0b, 0x01 },
	{ 0x0c, 0x15 }, { 0x0d, 0x15 }, { 0x0e, 0x17 }, { 0x0f, 0x17 },
	{ 0x10, 0x11 }, { 0x11, 0x11 }, { 0x12, 0x13 }, { 0x13, 0x13 },
	{ 0x14, 0x0d }, { 0x15, 0x0d }, { 0x20, 0x3c }, { 0x21, 0x20 },
	{ 0x22, 0x20 }, { 0x23, 0x21 }, { 0x24, 0x21 }, { 0x25, 0x3c },
	{ 0x26, 0x3c }, { 0x27, 0x04 }, { 0x28, 0x04 }, { 0x29, 0x0c },
	{ 0x2a, 0x0c }, { 0x2b, 0x00 }, { 0x2c, 0x14 }, { 0x2d, 0x14 },
	{ 0x2e, 0x16 }, { 0x2f, 0x16 }, { 0x30, 0x10 }, { 0x31, 0x10 },
	{ 0x32, 0x12 }, { 0x33, 0x12 }, { 0x34, 0x0d }, { 0x35, 0x0d },
	{ 0xee, 0x08 }, { 0x10, 0x00 }, { 0x12, 0xda }, { 0x14, 0x10 },
	{ 0x22, 0x69 }, { 0xee, 0x0f }, { 0x00, 0x01 }, { 0x01, 0x10 },
	{ 0xee, 0x00 }, { 0xea, 0x00 }, { 0xeb, 0x00 },
};

static inline struct r46h_panel *to_r46h_panel(struct drm_panel *panel)
{
	return container_of(panel, struct r46h_panel, panel);
}

static int r46h_panel_write_init_sequence(struct r46h_panel *ctx)
{
	unsigned int i;
	ssize_t ret;

	for (i = 0; i < ARRAY_SIZE(r46h_panel_init_commands); i++) {
		const struct r46h_panel_command *command =
			&r46h_panel_init_commands[i];

		ret = mipi_dsi_dcs_write(ctx->dsi, command->command,
					 &command->value, 1);
		if (ret < 0) {
			dev_err(&ctx->dsi->dev,
				"failed to write init command %u (0x%02x): %zd\n",
				i, command->command, ret);
			return ret;
		}
	}

	return 0;
}

static void
r46h_panel_read_handoff_state(struct r46h_panel *ctx,
			      struct r46h_panel_handoff_state *state)
{
	struct regulator *backlight =
		ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].consumer;
	struct regulator *power =
		ctx->supplies[R46H_PANEL_SUPPLY_POWER].consumer;

	state->reset_direction = gpiod_get_direction(ctx->reset_gpio);
	state->reset_raw = gpiod_get_raw_value_cansleep(ctx->reset_gpio);
	state->power_enabled = regulator_is_enabled(power);
	state->backlight_enabled = regulator_is_enabled(backlight);
	state->power_uv = regulator_get_voltage(power);
	state->backlight_uv = regulator_get_voltage(backlight);
}

static bool
r46h_panel_handoff_state_ready(const struct r46h_panel_handoff_state *state)
{
	return state->reset_direction == 0 && state->reset_raw == 1 &&
	       state->power_enabled > 0 && state->backlight_enabled > 0 &&
	       state->power_uv == R46H_PANEL_POWER_UV &&
	       state->backlight_uv == R46H_PANEL_BACKLIGHT_UV;
}

static int r46h_panel_disable_supplies(struct r46h_panel *ctx)
{
	struct regulator *backlight =
		ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].consumer;
	struct regulator *power =
		ctx->supplies[R46H_PANEL_SUPPLY_POWER].consumer;
	int ret;

	if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT]) {
		ret = regulator_disable(backlight);
		if (ret) {
			dev_err(ctx->panel.dev,
				"failed to disable backlight supply: %d\n", ret);
			/* Keep panel power on while the dependent rail is owned. */
			return ret;
		}

		ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = false;
	}

	if (ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER]) {
		ret = regulator_disable(power);
		if (ret) {
			dev_err(ctx->panel.dev,
				"failed to disable power supply: %d\n", ret);
			return ret;
		}

		ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = false;
	}

	return 0;
}

static int r46h_panel_assert_reset(struct r46h_panel *ctx)
{
	int ret;

	ret = gpiod_direction_output(ctx->reset_gpio, 1);
	if (ret)
		dev_err(ctx->panel.dev, "failed to assert reset: %d\n", ret);

	return ret;
}

static int r46h_panel_arm_bootloader_handoff(struct r46h_panel *ctx)
{
	struct regulator *backlight =
		ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].consumer;
	struct regulator *power =
		ctx->supplies[R46H_PANEL_SUPPLY_POWER].consumer;
	struct r46h_panel_handoff_state state;
	int cleanup_ret, reset_ret, ret;

	r46h_panel_read_handoff_state(ctx, &state);
	if (!r46h_panel_handoff_state_ready(&state)) {
		dev_info(ctx->panel.dev,
			 "R46H_PANEL_HANDOFF stage=probe decision=fallback reason=state reset_dir=%d reset_raw=%d power=%d backlight=%d power_uv=%d backlight_uv=%d\n",
			 state.reset_direction, state.reset_raw,
			 state.power_enabled, state.backlight_enabled,
			 state.power_uv, state.backlight_uv);
		return r46h_panel_assert_reset(ctx);
	}

	ret = regulator_enable(power);
	if (ret) {
		dev_err(ctx->panel.dev,
			"R46H_PANEL_HANDOFF stage=probe decision=error reason=power-ref error=%d\n",
			ret);
		reset_ret = r46h_panel_assert_reset(ctx);
		if (reset_ret)
			dev_err(ctx->panel.dev,
				"handoff reset rollback failed after power-ref error %d: %d\n",
				ret, reset_ret);
		return ret;
	}
	ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = true;

	ret = regulator_enable(backlight);
	if (ret) {
		dev_err(ctx->panel.dev,
			"R46H_PANEL_HANDOFF stage=probe decision=error reason=backlight-ref error=%d\n",
			ret);
		reset_ret = r46h_panel_assert_reset(ctx);
		cleanup_ret = r46h_panel_disable_supplies(ctx);
		if (reset_ret || cleanup_ret)
			dev_err(ctx->panel.dev,
				"handoff rollback failed after error %d: reset=%d supplies=%d\n",
				ret, reset_ret, cleanup_ret);
		return ret;
	}
	ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = true;

	/* Revalidate after both consumer references have been acquired. */
	r46h_panel_read_handoff_state(ctx, &state);
	if (!r46h_panel_handoff_state_ready(&state)) {
		dev_warn(ctx->panel.dev,
			 "R46H_PANEL_HANDOFF stage=probe decision=fallback reason=state-drift reset_dir=%d reset_raw=%d power=%d backlight=%d power_uv=%d backlight_uv=%d refs=2\n",
			 state.reset_direction, state.reset_raw,
			 state.power_enabled, state.backlight_enabled,
			 state.power_uv, state.backlight_uv);
		reset_ret = r46h_panel_assert_reset(ctx);
		cleanup_ret = r46h_panel_disable_supplies(ctx);
		if (reset_ret || cleanup_ret) {
			dev_err(ctx->panel.dev,
				"handoff fallback rollback failed: reset=%d supplies=%d\n",
				reset_ret, cleanup_ret);
			return reset_ret ? reset_ret : cleanup_ret;
		}
		msleep(20);
		return 0;
	}

	ctx->handoff_pending = true;

	dev_info(ctx->panel.dev,
		 "R46H_PANEL_HANDOFF stage=probe decision=adopt reset_dir=%d reset_raw=%d power=%d backlight=%d power_uv=%d backlight_uv=%d refs=2\n",
		 state.reset_direction, state.reset_raw, state.power_enabled,
		 state.backlight_enabled, state.power_uv, state.backlight_uv);
	return 0;
}

static int r46h_panel_prepare(struct drm_panel *panel)
{
	struct r46h_panel *ctx = to_r46h_panel(panel);
	struct regulator *backlight =
		ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].consumer;
	struct regulator *power =
		ctx->supplies[R46H_PANEL_SUPPLY_POWER].consumer;
	struct r46h_panel_handoff_state state;
	int cleanup_ret, ret;

	if (ctx->handoff_pending) {
		r46h_panel_read_handoff_state(ctx, &state);
		ctx->handoff_pending = false;
		if (r46h_panel_handoff_state_ready(&state)) {
			ctx->handoff_active = true;
			ctx->handoff_used = true;
			ctx->initialized = true;
			dev_info(panel->dev,
				 "R46H_PANEL_HANDOFF stage=prepare action=preserve reset_raw=%d power=%d backlight=%d\n",
				 state.reset_raw, state.power_enabled,
				 state.backlight_enabled);
			return 0;
		}

		dev_warn(panel->dev,
			 "R46H_PANEL_HANDOFF stage=prepare action=fallback-full-init reason=state-drift reset_dir=%d reset_raw=%d power=%d backlight=%d power_uv=%d backlight_uv=%d\n",
			 state.reset_direction, state.reset_raw,
			 state.power_enabled, state.backlight_enabled,
			 state.power_uv, state.backlight_uv);
		ret = r46h_panel_assert_reset(ctx);
		cleanup_ret = r46h_panel_disable_supplies(ctx);
		if (ret || cleanup_ret)
			return ret ? ret : cleanup_ret;
		msleep(20);
	}

	if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||
	    ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER]) {
		ret = r46h_panel_disable_supplies(ctx);
		if (ret) {
			dev_err(panel->dev,
				"failed to clear residual supply state: %d\n", ret);
			return ret;
		}

		msleep(20);
	}

	ret = r46h_panel_assert_reset(ctx);
	if (ret)
		return ret;

	ret = regulator_enable(power);
	if (ret) {
		dev_err(panel->dev, "failed to enable power supply: %d\n", ret);
		return ret;
	}
	ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = true;

	ret = regulator_enable(backlight);
	if (ret) {
		dev_err(panel->dev, "failed to enable backlight supply: %d\n",
			ret);
		goto disable_supplies;
	}
	ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = true;

	msleep(20);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	msleep(150);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	msleep(20);

	ret = r46h_panel_write_init_sequence(ctx);
	if (ret)
		goto disable_supplies;

	ret = mipi_dsi_dcs_exit_sleep_mode(ctx->dsi);
	if (ret < 0) {
		dev_err(panel->dev, "failed to exit sleep mode: %d\n", ret);
		goto disable_supplies;
	}

	msleep(200);

	ret = mipi_dsi_dcs_set_display_on(ctx->dsi);
	if (ret < 0) {
		dev_err(panel->dev, "failed to turn display on: %d\n", ret);
		goto disable_supplies;
	}

	msleep(20);
	ctx->initialized = true;

	return 0;

disable_supplies:
	r46h_panel_assert_reset(ctx);
	cleanup_ret = r46h_panel_disable_supplies(ctx);
	if (cleanup_ret)
		dev_err(panel->dev,
			"failed to disable supplies while handling error %d: %d\n",
			ret, cleanup_ret);

	msleep(20);
	return ret;
}

static int r46h_panel_enable(struct drm_panel *panel)
{
	struct r46h_panel *ctx = to_r46h_panel(panel);

	if (!ctx->initialized) {
		dev_err(panel->dev, "refusing to enable uninitialized panel\n");
		return -EIO;
	}
	if (ctx->handoff_active) {
		ctx->handoff_active = false;
		dev_info(panel->dev,
			 "R46H_PANEL_HANDOFF stage=enable action=consume-first-enable\n");
		return 0;
	}

	/* Preserve the downstream delay between display-on and backlight-on. */
	msleep(120);
	return 0;
}

static int r46h_panel_disable(struct drm_panel *panel)
{
	/* drm_panel_disable() has already disabled the external backlight. */
	msleep(50);
	return 0;
}

static int r46h_panel_unprepare(struct drm_panel *panel)
{
	struct r46h_panel *ctx = to_r46h_panel(panel);
	int disable_ret, ret;

	if (ctx->initialized) {
		ret = mipi_dsi_dcs_set_display_off(ctx->dsi);
		if (ret < 0)
			dev_err(panel->dev, "failed to turn display off: %d\n",
				ret);

		msleep(20);

		ret = mipi_dsi_dcs_enter_sleep_mode(ctx->dsi);
		if (ret < 0)
			dev_err(panel->dev, "failed to enter sleep mode: %d\n",
				ret);

		usleep_range(10000, 15000);
		ctx->initialized = false;
	}

	r46h_panel_assert_reset(ctx);
	disable_ret = r46h_panel_disable_supplies(ctx);
	if (disable_ret)
		dev_err(panel->dev, "failed to disable panel supplies: %d\n",
			disable_ret);
	msleep(20);
	ctx->handoff_pending = false;
	ctx->handoff_active = false;
	if (ctx->handoff_used) {
		ctx->handoff_used = false;
		dev_info(panel->dev,
			 "R46H_PANEL_HANDOFF stage=unprepare next=full-init\n");
	}

	/*
	 * The Rockchip panel bridge does not recover from an unprepare error.
	 * Keep residual consumer refs in supply_enabled[] so the next prepare
	 * retries cleanup, but return success so DRM clears panel->prepared.
	 */
	return 0;
}

static const struct drm_display_mode r46h_panel_mode = {
	.clock = 60000,
	.hdisplay = 1024,
	.hsync_start = 1024 + 80,
	.hsync_end = 1024 + 80 + 60,
	.htotal = 1024 + 80 + 60 + 86,
	.vdisplay = 768,
	.vsync_start = 768 + 16,
	.vsync_end = 768 + 16 + 8,
	.vtotal = 768 + 16 + 8 + 8,
	.flags = DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_NVSYNC,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int r46h_panel_get_modes(struct drm_panel *panel,
				struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &r46h_panel_mode);
	if (!mode)
		return -ENOMEM;

	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);

	connector->display_info.bpc = 8;
	connector->display_info.width_mm = 52;
	connector->display_info.height_mm = 70;
	connector->display_info.bus_flags =
		DRM_BUS_FLAG_DE_LOW | DRM_BUS_FLAG_PIXDATA_DRIVE_NEGEDGE;

	return 1;
}

static const struct drm_panel_funcs r46h_panel_funcs = {
	.prepare = r46h_panel_prepare,
	.enable = r46h_panel_enable,
	.disable = r46h_panel_disable,
	.unprepare = r46h_panel_unprepare,
	.get_modes = r46h_panel_get_modes,
};

static int r46h_panel_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct r46h_panel *ctx;
	int ret;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;

	ctx->dsi = dsi;
	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio),
				     "failed to get reset GPIO\n");

	ctx->supplies[R46H_PANEL_SUPPLY_POWER].supply = "power";
	ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].supply = "backlight";
	ret = devm_regulator_bulk_get(dev, R46H_PANEL_NUM_SUPPLIES,
				      ctx->supplies);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get panel supplies\n");

	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	/* Preserve downstream dsi,flags BIT(9): disable EoT packets in HS mode. */
	dsi->mode_flags = MIPI_DSI_MODE_VIDEO |
			  MIPI_DSI_MODE_VIDEO_BURST |
			  MIPI_DSI_MODE_NO_EOT_PACKET |
			  MIPI_DSI_MODE_LPM;
	dev_info(dev,
		 "R46H_DSI_CFG lanes=%u format=%u mode_flags=0x%08lx\n",
		 dsi->lanes, dsi->format, dsi->mode_flags);

	mipi_dsi_set_drvdata(dsi, ctx);
	drm_panel_init(&ctx->panel, dev, &r46h_panel_funcs,
		       DRM_MODE_CONNECTOR_DSI);

	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get backlight\n");

	ret = r46h_panel_arm_bootloader_handoff(ctx);
	if (ret)
		return ret;

	drm_panel_add(&ctx->panel);

	ret = mipi_dsi_attach(dsi);
	if (ret) {
		int cleanup_ret;
		int reset_ret;

		ctx->handoff_pending = false;
		reset_ret = r46h_panel_assert_reset(ctx);
		cleanup_ret = r46h_panel_disable_supplies(ctx);
		if (reset_ret || cleanup_ret)
			dev_err(dev,
				"failed to rollback panel after attach error %d: reset=%d supplies=%d\n",
				ret, reset_ret, cleanup_ret);
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(dev, ret, "failed to attach to DSI host\n");
	}

	return 0;
}

static void r46h_panel_remove(struct mipi_dsi_device *dsi)
{
	struct r46h_panel *ctx = mipi_dsi_get_drvdata(dsi);
	int ret;

	/* Only a failed prepare can leave owned refs while unprepared. */
	if (!ctx->panel.prepared &&
	    (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||
	     ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER])) {
		r46h_panel_assert_reset(ctx);
		ret = r46h_panel_disable_supplies(ctx);
		if (ret)
			dev_err(&dsi->dev,
				"failed to release residual panel supplies: %d\n",
				ret);
		msleep(20);
	}

	ret = mipi_dsi_detach(dsi);
	if (ret)
		dev_err(&dsi->dev, "failed to detach from DSI host: %d\n", ret);

	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id r46h_panel_of_match[] = {
	{ .compatible = "gameconsole,r46h-panel" },
	{ }
};
MODULE_DEVICE_TABLE(of, r46h_panel_of_match);

static struct mipi_dsi_driver r46h_panel_driver = {
	.probe = r46h_panel_probe,
	.remove = r46h_panel_remove,
	.driver = {
		.name = "panel-r46h",
		.of_match_table = r46h_panel_of_match,
	},
};
module_mipi_dsi_driver(r46h_panel_driver);

MODULE_AUTHOR("OpenAI Codex");
MODULE_DESCRIPTION("R46H 1024x768 MIPI-DSI panel driver");
MODULE_LICENSE("GPL");

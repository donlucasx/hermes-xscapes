# xscapes for Hermes

A small ASCII scene that runs under Hermes in your terminal and shows what the agent is doing while you wait.

- The work is the weather: the harder Hermes works, the higher the sea (or the wind on the mountains, or the rain on the window).
- Each subagent is a little one of the companion's kind (a crablet, a kitten or an owlet) that arrives and leaves with it.
- The moon sinks as the context window fills, and finished todos light up as stars.
- When Hermes finishes or needs your approval, the companion knocks, with a sound, so you can look away and still know.
- The sky follows your real time of day.

This plugin forwards Hermes's lifecycle hooks to the xscapes program, which draws the scene.

## Install

1. Install xscapes (macOS and Linux) with the one-line installer on
   https://donlucasx.github.io/xscapes/, or download a binary from
   https://github.com/donlucasx/xscapes/releases/latest and put it on your PATH.
   This plugin needs xscapes 0.5.1 or later.

2. Install the plugin:

   ```
   hermes plugins install donlucasx/hermes-xscapes --enable
   ```

   (Once the plugin is listed in the Hermes catalog, `hermes plugins install xscapes` works too.)

3. Run Hermes inside the scene:

   ```
   xscapes hermes
   ```

Pick a scene with `xscapes scape vista`, `xscapes scape shore` or `xscapes scape harbour`, and a companion with `xscapes companion crab` or `xscapes companion cat`. A running scene switches on its next frame.

If you set up xscapes before with `xscapes install hermes`, those shell hooks and this plugin would both send every event. Run `xscapes uninstall hermes` to keep the plugin only; the plugin logs a warning when it finds both.

## What it does on your machine

- **Runs a program.** On each hook it starts `xscapes hook <event> hermes` and writes the event to its stdin as JSON (the same fields Hermes's own shell hooks send). It does not wait for the program, and it never blocks, edits or approves anything.
- **Finds the program** in `XSCAPES_BIN`, then on `PATH`, then at `~/.local/bin/xscapes`. Without it, every hook does nothing and one warning is logged.
- **Reads one file outside its own folder:** Hermes's `config.yaml`, only to check for the old xscapes shell hooks and warn about double events.
- **Keeps model calls to their numbers.** After each model call it passes on only the token usage, the model's name and the context window size, never the response or the message, plus its own running token total for the session.
- **Sends nothing over the network.** xscapes keeps the events in `~/.config/xscapes/` on your machine.

What xscapes sees: the event name, the tool name and its arguments, your prompt's first line and the reply's first line, durations, and the session id. It uses them to draw the scene and the activity line under it.

## Events

`on_session_start`, `on_session_reset`, `on_session_end`, `on_session_finalize`, `pre_llm_call`, `post_llm_call`, `pre_tool_call`, `post_tool_call`, `pre_approval_request`, `post_approval_response`, `subagent_start`, `subagent_stop`.

## Tests

```
~/.hermes/hermes-agent/venv/bin/python -m pytest tests
hermes plugins validate .
```

MIT licensed. xscapes: https://github.com/donlucasx/xscapes

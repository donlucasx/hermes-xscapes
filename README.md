<p align="center">
  <img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/readme/cover.gif" alt="xscapes: a thinking screen for terminal agents" width="100%">
</p>

# xscapes for Hermes

Living ASCII scenes that react as Hermes works. The scene runs under Hermes in
your terminal and shows what the agent is doing while you wait.

<p align="center">
  <img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/hermes/reveal.gif" alt="Hermes running above the mountain vista" width="100%">
</p>

<table>
  <tr>
    <td width="50%"><img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/hermes/owlets.gif" alt="owlets arrive for Hermes's subagents"><br><b>Subagents</b> arrive as owlets, crablets or kittens, and leave when they finish.</td>
    <td width="50%"><img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/hermes/think.gif" alt="a thought cloud over the cat"><br><b>Thinking.</b> A thought cloud rises over the cat while the model thinks.</td>
  </tr>
  <tr>
    <td><img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/hermes/ask.gif" alt="the cat asks: allow chmod?"><br><b>It asks when it needs you.</b> Approvals, questions and password prompts raise a balloon and a sound.</td>
    <td><img src="https://raw.githubusercontent.com/donlucasx/xscapes/main/assets/hermes/scenes.gif" alt="the three scenes"><br><b>Three scenes</b>, each with its companion: the vista and the owl, the shore and the crab, the harbour and the cat.</td>
  </tr>
</table>

The harder Hermes works, the stronger the wind, the higher the sea or the
heavier the rain. The moon sinks as the context window fills, finished todos
light up as stars, and the companion knocks when Hermes finishes.

## Install

1. Install xscapes (macOS and Linux) with the one-line installer on
   https://donlucasx.github.io/xscapes/, or download a binary from
   https://github.com/donlucasx/xscapes/releases/latest and put it on your
   PATH. This plugin needs xscapes 0.5.1 or later.

2. Install the plugin:

   ```
   hermes plugins install donlucasx/hermes-xscapes --enable
   ```

   Once the Hermes catalog lists it, `hermes plugins install xscapes` works too.

3. Run Hermes inside the scene:

   ```
   xscapes hermes
   ```

Switch scenes with `xscapes scape vista|shore|harbour` and companions with
`xscapes companion crab|cat`. A running scene switches on its next frame.

If you set up xscapes earlier with `xscapes install hermes`, run
`xscapes uninstall hermes`, or every event arrives twice (the plugin logs a
warning when it finds both).

## What it does on your machine

- **Runs a program.** On each hook it starts `xscapes hook <event> hermes` and
  writes the event to its stdin as JSON (the same fields Hermes's shell hooks
  send). It doesn't wait for it, and never blocks, edits or approves anything.
- **Finds the program** in `XSCAPES_BIN`, then on `PATH`, then at
  `~/.local/bin/xscapes`. Without it, every hook does nothing and logs one
  warning.
- **Reads one file outside its folder:** Hermes's `config.yaml`, to warn about
  the old shell hooks.
- **Keeps model calls to their numbers.** After each model call it passes on
  only the token usage, the model's name and the context window size, never
  the response or the message, plus its own running token total for the
  session.
- **Keeps the conversation in Hermes.** From each turn it sends only the
  first line of your prompt and of the reply, cut to 120 characters, never
  the conversation history.
- **Gives xscapes a minimal environment:** `PATH`, `HOME`, `LANG`, `LC_ALL`,
  `TERM`, `XDG_CONFIG_HOME`, `TMPDIR` and xscapes's own `XSCAPES_*` settings.
  Your provider keys and the rest of Hermes's environment never reach it.
- **Sends nothing over the network.** xscapes keeps events in
  `~/.config/xscapes/` on your machine.

xscapes sees the event name, the tool name and its arguments, that first line
of your prompt and of the reply, durations, and the session id, and uses them
to draw the scene and its activity line.

## Events

`on_session_start`, `on_session_reset`, `on_session_end`, `on_session_finalize`,
`pre_llm_call`, `post_llm_call`, `pre_tool_call`, `post_tool_call`,
`pre_approval_request`, `post_approval_response`, `subagent_start`,
`subagent_stop`, `on_human_input_request`, `on_human_input_resolved`,
`post_api_request`.

## Tests

```
~/.hermes/hermes-agent/venv/bin/python -m pytest tests
hermes plugins validate .
```

MIT. xscapes: https://github.com/donlucasx/xscapes

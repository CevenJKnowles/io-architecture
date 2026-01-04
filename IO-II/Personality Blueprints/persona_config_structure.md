# Io Persona / ICP Config Directory Structure (GitHub Layout)

This is a **suggested** repository layout for storing the Io Persona v1.3 and
Io–Ceven Collaborative Protocol (ICP v1.0) configuration files.

You can adapt names and paths, but keeping a consistent structure makes it
easier to reuse across tools and hosts.

```text
your-repo-root/
├── persona/
│   ├── io/
│   │   ├── Io_v1_3_Implementable_Spec.md
│   │   ├── Io_v1_3_Config.json
│   │   ├── Io_v1_3_Config.csv
│   │   ├── Io_v1_3_Persona_Config.py
│   │   └── Io_v1_3_Persona_Notebook.ipynb
│   ├── protocols/
│   │   ├── ICP_v1_0.md
│   │   ├── ICP_v1_0.json
│   │   ├── ICP_v1_0.csv
│   │   ├── ICP_v1_0.py
│   │   └── ICP_v1_0.ipynb
│   └── install/
│       ├── io_persona_setup.py
│       └── Io_Persona_Installer.ipynb
├── README.md
└── (other project files...)
```

## Notes

- `persona/io/` holds **persona definition artifacts** (Io v1.3).
- `persona/protocols/` holds **collaboration & governance artifacts** (ICP v1.0).
- `persona/install/` holds scripts and notebooks used to:
  - test the persona,
  - connect to different LLM backends (e.g., OpenAI, LM Studio),
  - and quickly instantiate Io with the correct system prompt.

If you want a minimal setup, you can also flatten everything into `persona/`:

```text
persona/
├── Io_v1_3_Config.json
├── Io_v1_3_Implementable_Spec.md
├── ICP_v1_0.json
├── ICP_v1_0.md
├── io_persona_setup.py
└── Io_Persona_Installer.ipynb
```

Just ensure that the paths in your scripts / notebooks match the actual location
of the config files.

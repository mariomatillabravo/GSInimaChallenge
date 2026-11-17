# ADR-0012: Front-end stack and tooling

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

The web interface lets a user pick a station, a time range, an aggregation level and the measurements, and shows
the result as a table and as charts. It lives in the same repository as the API, under `frontend/`, and has to be:

- type-safe end to end, with the same strictness as the backend (mypy in strict mode);
- easy to run for a reviewer, without CORS or environment tweaks;
- small enough to be read and explained file by file.

The tooling landscape adds a constraint. TypeScript 7 (July 2026) is a native rewrite whose npm package no longer
exposes the compiler's JavaScript API, which the type-aware linter (typescript-eslint, TypeScript `<6.1`) and the
type generator chosen for the API client (openapi-typescript, TypeScript 5) depend on. The official Vite template
already uses TypeScript 7 with oxlint instead of ESLint.

## Options considered

**Framework and build tool**

1. **React + Vite**: a client-side application served as static files; Vite gives a fast dev server with a proxy
   and a production build. React is the team's known framework.
2. **Next.js**: server-side rendering and routing are not needed for one interactive page, and it adds a Node server
   to deploy.
3. **Angular, Vue or Svelte**: valid choices with no advantage here, and less familiar.

**TypeScript version and linting**

1. **TypeScript 5.9 + ESLint with typescript-eslint**: every tool supports it today, and type-aware lint rules work.
   One major version behind.
2. **TypeScript 7 + oxlint**: the newest and fastest, as in the Vite template, but oxlint's type-aware rules are
   young and openapi-typescript cannot run on TypeScript 7.
3. **TypeScript 6 + ESLint**: typescript-eslint supports it, but openapi-typescript declares TypeScript 5 as a peer
   dependency, so npm refuses to install it without forcing an override. TypeScript 6 is a transition release.

**How the browser reaches the API**

1. **Same origin through a proxy**: the page calls relative URLs (`/api/...`); in development Vite forwards them to
   the backend, and in Docker a web server does the same.
2. **Cross-origin calls with CORS**: the backend would need a CORS policy, and every custom response header the page
   reads (such as `X-Request-ID`) would have to be listed in `Access-Control-Expose-Headers`.

**Styling**

1. **CSS Modules with design tokens and native form controls**: plain CSS scoped per component, shared colours and
   spacing as CSS custom properties, the browser's own date and time inputs.
2. **Tailwind CSS**: fast to write, but another vocabulary and build step for a handful of components.
3. **A component library (MUI, Mantine)**: ready-made widgets, at the cost of a much larger bundle and of fighting
   its styles; its date picker would replace a native input that already does the job.

## Decision

- **React 19 + Vite**, a static single-page application.
- **TypeScript 5.9**, with `strict` and `noUncheckedIndexedAccess`, so that reading `rows[i]` yields
  `Row | undefined` and an index out of range has to be handled.
- **ESLint** with typescript-eslint at its strictest type-aware level (`strictTypeChecked` and
  `stylisticTypeChecked`), plus the React hooks and React Refresh rules. **Prettier** owns formatting, and
  `eslint-config-prettier` switches off the ESLint rules that would overlap with it.
- **Vitest** with **Testing Library** and **jsdom**: Vitest reuses the Vite configuration, and tests find elements
  by their accessible role, as a user would.
- **Same origin through a proxy**. Vite forwards `/api` to `http://127.0.0.1:8000` rather than `localhost`: Node
  resolves `localhost` to the IPv6 address `::1` first (verified on Windows), where uvicorn does not listen by
  default, and the explicit address avoids depending on the fallback to IPv4. In Docker Compose, nginx serves the
  built app and forwards `/api/` to the `api` service in the same way.
- **CSS Modules** with tokens in `src/styles/global.css`. The first version had a light and a dark theme that
  followed the system setting; it was replaced by a single colour scheme (Sapphire Blue background, Ocean Cyan for
  interactive states, Neon Jade highlights), with every text and line checked against the WCAG contrast minimums.
- **Node.js 26** (LTS since October 2026), pinned by major version in `frontend/.nvmrc` and `engines`, and npm with
  a committed `package-lock.json` installed through `npm ci`.

## Consequences

- Moving to TypeScript 7 is a version bump in `package.json` once typescript-eslint and openapi-typescript support
  it; no code depends on the version.
- The API needs no CORS configuration, and the same relative URLs work in development and in Docker.
- CSS Module class names are typed as any string, so a misspelt class name is not a compile error; it only shows as
  a missing style.
- Native date and time inputs look slightly different in each browser, and they hold local wall-clock times without
  a time zone, which the client sends as Europe/Madrid times, the API's default.
- The front-end has its own CI job (lint, type check, tests and production build), and `make check` runs it together
  with the backend checks.

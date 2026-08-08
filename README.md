# mixomics-org.github.io

Organisation site for [mixOmics.org](https://github.com/mixOmics-org).

This repository serves two purposes:

1. **Landing page** at the root of the custom domain (`index.html`).
2. **Domain root for all project sites.** Because this is the organisation site,
   its custom domain becomes the root for every Pages site in the organisation.
   `mixOmics-Vignette` is served at `<domain>/mixOmics-Vignette/` without any
   configuration in that repository.

## Consequences

- Changing the custom domain here changes the URL of **every** project site in
  the organisation. Do not change it casually.
- A project repository containing its own `CNAME` file overrides the inherited
  domain for that repository only.
- Only one organisation site is permitted per account.

## Adding a guide

Add a card to `index.html` pointing at `/<repository-name>/`. The project
repository publishes itself; nothing else is needed here.

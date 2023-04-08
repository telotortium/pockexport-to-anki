# Pockexport-to-Anki

A simple package to take the JSON output of the
[Pockexport](https://github.com/karlicoss/pockexport) command and create
[Anki](https://apps.ankiweb.net/) notes. These notes can then be reviewed, in
order to review past Pocket saves and thus get acquainted with what you were
reading, perhaps even years.

This project was directly inspired by and hopes to implement, in a quick and
dirty way, the ["Archive
Revisiter"](https://gwern.net/note/statistic#program-for-non-spaced-repetition-review-of-past-written-materials-for-serendipity-rediscovery-archive-revisiter)
idea proposed by Gwern on his site many years ago.

For now, this is for personal use, so the script assumes details of my Anki
decks. A few of the notable features:

- Cards are suspended in Anki (thus disabling review) if the corresponding
  Pocket item is archived and *not favorited*.
- The favorite status in Pocket is synced to the "marked" tag in Anki (which
  shows a star in Anki interfaces, and so plays exactly the same role).
- Tags from each Pocket item are synced to the corresponding Anki note.
- (To be implemented) Sync changes made to the Anki note/card back to Pocket
  using the [Pocket Python package](https://github.com/tapanpandita/pocket).
  - Suspended status, favorite tag, other tags.

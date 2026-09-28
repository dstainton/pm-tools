# Partner

A partner reads a page you are willing to forward. The page names the work
they are allowed to see, in plain status words. It leaves out ticket keys,
links, and people's names unless the settings say otherwise.

The brief for that meeting stays with you. The report and the release notes
are the pages you can send.

## Mark what they may see

An Epic they should see carries the label `partner-visible`, or the
workstream is marked partner-visible. A page they should see carries the
same label. Anything labelled `internal` stays out of the release notes.
Those names live under `audiences.partner` in the settings file.

## Write the page

```text
pm report --audience partner
pm release-notes --audience partner --since 2026-08-01
```

Each audience has its own file and its own memory. A partner report does
not move the window of your product-management report.

Send it after you have read it:

```text
pm publish ~/.pm-tools/out/weekly_report_partner_2026-09-28.md
```

## Prepare the meeting

```text
pm brief --for "Partner review" --audience partner
```

The file says it is internal. It is the list you walk in with. It is not
the page you forward.

`pm metrics` has no partner view. The command stops if you ask for one.

## One team

```text
pm report --workstream SDX --audience partner
```

A partner who only shares some of the products in a file should use
`--product` or `--workstream`, the same way [leadership](leadership.md)
does. Teams that do not share a Jira project need one settings file each.
That pattern is written out on the leadership page.

## The setting

```yaml
role: partner
```

`pm report` is then the partner page. Comment authors and decision owners
are left off before the partner pass removes any person name that still
reached the prose. The design is in the [plan](../ROLE_REPORTS_PLAN.md).

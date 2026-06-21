# APIReaper

<img width="836" height="624" alt="General Pic" src="https://github.com/user-attachments/assets/5f5fee9e-cf6f-4f81-a5ed-a2ec1ee10800" />


APIReaper is a Burp Suite extension for importing API endpoint collections and turning them into editable HTTP requests. It is designed for API security testing workflows where you need to quickly review, modify, filter, and send large sets of requests to Burp Repeater or Intruder.

The extension supports Postman collections, Swagger/OpenAPI documents, HAR exports, Insomnia exports, and simple JSON endpoint lists.

![APIReaper Workspace](https://github.com/user-attachments/assets/b5449fdf-1c2d-49dc-801b-2a20a59a6769)

> Main Workspace tab with imported endpoints, request editor, filters, and action menu.

## Features

### Import API Documents

APIReaper can import endpoint data from multiple sources:

- Postman collections
- Swagger/OpenAPI specs
- HAR files
- Insomnia exports
- Simple JSON request lists

Imported endpoints are converted into raw HTTP requests that can be reviewed and edited inside Burp.

![Import Flow](docs/images/import-flow.png)

> Screenshot placeholder: Import button and loaded endpoint tree.

### Editable Request Workspace

Each endpoint opens in its own request tab. The editor includes separate views for:

- Raw request
- Headers
- Body

Changes are synchronized between the Raw, Headers, and Body views.

![Request Editor](docs/images/request-editor.png)

> Screenshot placeholder: request tab showing Raw, Headers, and Body sub-tabs.

### Modified Request Tracking

Edited requests are tracked automatically:

- Modified requests are marked in the tree
- Modified tab titles are marked
- Modified count is shown in the toolbar
- Reset button restores the original generated request

### Token Profiles

APIReaper includes quick auth profiles for switching between common API testing contexts:

- Custom
- No Auth
- User Token
- Admin Token

This is useful for broken access control, IDOR, and role-based authorization testing.

```text
Authorization: Bearer {{USER_TOKEN}}
Authorization: Bearer {{ADMIN_TOKEN}}
```

![Auth Profiles](docs/images/auth-profiles.png)

> Screenshot placeholder: Auth Profile dropdown with User Token and Admin Token selected.

### Advanced Filters

Filters are available in a separate dialog to keep the main UI clean. You can filter endpoints by:

- HTTP method
- Endpoint name or request line
- Body parameter name
- Modified-only requests

The filter summary is shown in the main toolbar.

![Filters Dialog](docs/images/filters-dialog.png)

> Screenshot placeholder: Filters window with method checkboxes and search fields.

### JSON Body Utilities

The Body editor includes quick actions for API payload work:

- Pretty JSON
- Minify JSON
- Copy Body

These actions help when preparing payloads for Repeater, Intruder, or manual testing.

![Body Tools](docs/images/body-tools.png)

> Screenshot placeholder: Body tab toolbar with Pretty JSON, Minify, and Copy Body.

### Send to Burp Tools

APIReaper can send requests directly to Burp:

- Send selected request to Repeater
- Send selected request to Intruder
- Send all visible/filtered requests to Repeater
- Send only modified visible requests to Repeater

Requests sent to Repeater are named using:

```text
[Group] Request Name
```

This makes large API test sessions easier to organize inside Burp.

### Document Summary

The Document Summary tab helps review imported API documents at a higher level. It summarizes:

- Endpoints
- Query parameters
- Request body parameters
- Response body parameters

![Document Summary](docs/images/document-summary.png)

> Screenshot placeholder: Document Summary tab with endpoint and parameter tables.

### About Tab

The About tab includes project information, author details, GitHub link, and LinkedIn link.

![About Tab](docs/images/about-tab.png)

> Screenshot placeholder: About tab with APIReaper title and social links.

## Installation

1. Open Burp Suite.
2. Go to `Extensions`.
3. Add a new extension.
4. Select extension type `Python`.
5. Choose `APIReaper.py`.
6. Make sure Jython is configured in Burp Suite.

## Usage

1. Set the target `Base URL`.
2. Choose an `Auth Profile` or enter a custom auth header.
3. Click `Import`.
4. Select your API document.
5. Open endpoints from the tree.
6. Edit the request in Raw, Headers, or Body view.
7. Use filters to narrow down endpoints.
8. Send selected, modified, or filtered requests to Repeater.

## Supported Input Examples

### OpenAPI / Swagger

```json
{
  "openapi": "3.0.0",
  "paths": {
    "/users/{id}": {
      "get": {
        "summary": "Get user by ID"
      }
    }
  }
}
```

### Simple JSON List

```json
[
  {
    "method": "GET",
    "path": "/api/users",
    "name": "List Users"
  }
]
```

## Security Notes

APIReaper is built for security testing workflows. Be careful when importing real production collections:

- Review generated requests before sending them.
- Avoid committing real tokens or secrets.
- Use token placeholders such as `{{USER_TOKEN}}` and `{{ADMIN_TOKEN}}`.
- Confirm batch sends before sending large request sets to Burp Repeater.

## Roadmap Ideas

Potential future improvements:

- IDOR helper
- Mass assignment variant generator
- Intruder payload position builder
- Sensitive endpoint highlighting
- Local AI assistant for endpoint risk triage
- Workspace save/load support
- Parameter inventory export

## Author

Created by **Soheil Rajaei**.

- GitHub: [rjsoheil](https://github.com/rjsoheil/)
- LinkedIn: [Soheil Rajaei](https://www.linkedin.com/in/soheil-rajaei-1b0805243/)

## License

Add your preferred license here.


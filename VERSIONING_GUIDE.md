# Message Versioning & Diffing Guide

This document provides an overview of the message versioning and diffing system implemented in the Origin Project.

## 1. Overview

To ensure conversational integrity and provide a clear audit trail, user messages can be edited, and each edit creates a new version of the message. The system stores all previous versions, allowing users to view the history of changes.

This functionality consists of three main parts:
1.  **Data Model:** A new `message_versions` table in the database stores historical copies of messages.
2.  **API Endpoints:** A set of endpoints to handle editing messages and retrieving version history.
3.  **Frontend UI:** A modal dialog with a diff viewer to visualize the changes between any two versions of a message.

## 2. Backend Implementation

### Data Model
-   A new table, `message_versions`, was added via the `f1b2c3d4e5f6` migration.
-   It stores the content, role, and a timestamp for each historical version, linked via a foreign key to the original `message_id`.

### API Endpoints

-   **`PUT /api/messages/{message_id}`:**
    -   Handles the editing of a message.
    -   Before updating the message in the main `messages` table, it first saves the *current* state of the message into the `message_versions` table.
    -   This endpoint is protected and ensures only the original author of the message can edit it.

-   **`GET /api/messages/{message_id}/versions`:**
    -   Retrieves a list of all historical versions for a given message, ordered by creation date.
    -   This is used by the frontend to populate the version selection UI in the diff modal.

## 3. Frontend Implementation

-   **Message History Button:** A "History" button now appears on user messages when hovered over.
-   **Diff View Modal (`DiffViewModal.jsx`):**
    -   When the history button is clicked, this modal opens.
    -   It fetches all available versions using the `/versions` endpoint.
    -   It provides a UI with radio buttons for the user to select any two versions to compare (an "old" and a "new" version).
    -   It uses the `react-diff-viewer` library to render a clear, split-view visualization of the differences between the selected versions.
    -   This provides a powerful and intuitive way for users to track changes and understand the evolution of a conversation.

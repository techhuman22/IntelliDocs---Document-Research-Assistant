# Authentication API — Example Requests & Responses

Base URL: `http://localhost:8000/api/v1`

---

## 1. Register

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "full_name": "Jane Doe",
  "email": "jane@example.com",
  "password": "MyStr0ng!Pass"
}
```

**201 Created**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "jane@example.com",
  "full_name": "Jane Doe",
  "is_active": true,
  "is_verified": false,
  "plan_tier": "free",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**409 Conflict** (email already registered)
```json
{
  "error": {
    "code": "EMAIL_ALREADY_EXISTS",
    "message": "An account with email 'jane@example.com' already exists.",
    "details": { "field": "email" }
  }
}
```

**422 Unprocessable Entity** (weak password)
```json
{
  "error": {
    "code": "REQUEST_VALIDATION_ERROR",
    "message": "Request data failed validation.",
    "details": {
      "errors": [
        {
          "field": "password",
          "message": "Password must contain: at least one uppercase letter (A-Z), at least one digit (0-9).",
          "type": "value_error"
        }
      ]
    }
  }
}
```

---

## 2. Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "jane@example.com",
  "password": "MyStr0ng!Pass"
}
```

**200 OK**
```json
{
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 900
  },
  "user": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "email": "jane@example.com",
    "full_name": "Jane Doe",
    "is_active": true,
    "is_verified": false,
    "plan_tier": "free",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
}
```

**401 Unauthorized** (wrong credentials)
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid email or password.",
    "details": {}
  }
}
```

---

## 3. Authenticated Request (using the access token)

```http
GET /api/v1/users/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**200 OK**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "jane@example.com",
  "full_name": "Jane Doe",
  "is_active": true,
  "is_verified": false,
  "plan_tier": "free",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**401 Unauthorized** (missing or invalid token)
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required. Provide a Bearer token in the Authorization header.",
    "details": {}
  }
}
```

---

## 4. Refresh Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**200 OK** (new token pair — old refresh token is now invalid)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**401 Unauthorized** (token already used / expired)
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "Refresh token has already been used or has expired.",
    "details": {}
  }
}
```

---

## 5. Logout

```http
POST /api/v1/auth/logout
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**200 OK**
```json
{
  "message": "Successfully logged out."
}
```

---

## 6. Update Profile

```http
PATCH /api/v1/users/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "full_name": "Jane Smith"
}
```

**200 OK**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "jane@example.com",
  "full_name": "Jane Smith",
  "is_active": true,
  "is_verified": false,
  "plan_tier": "free",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

---

## 7. Change Password

```http
POST /api/v1/users/me/change-password
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "current_password": "MyStr0ng!Pass",
  "new_password": "NewStr0ng!Pass",
  "confirm_new_password": "NewStr0ng!Pass"
}
```

**200 OK**
```json
{
  "message": "Password changed successfully. All active sessions have been revoked."
}
```

**403 Forbidden** (wrong current password)
```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Current password is incorrect.",
    "details": {}
  }
}
```

---

## 8. Delete Account

```http
DELETE /api/v1/users/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "password": "MyStr0ng!Pass"
}
```

**200 OK**
```json
{
  "message": "Account permanently deleted."
}
```

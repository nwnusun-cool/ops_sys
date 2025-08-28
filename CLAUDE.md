# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Flask-based OpenStack management web application that provides unified management of multiple OpenStack clusters. The system allows administrators to manage instances, volumes, snapshots, and SSH connections across different OpenStack environments.

## Development Commands

### Environment Setup
```bash
cd app
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac  
source venv/bin/activate
pip install -r requirements.txt
```

### Running the Application
```bash
cd app
python app.py
# Server runs on http://0.0.0.0:5001
```

### Configuration
- Main config: `app/config/config.json` - Contains OpenStack environments and security settings
- **IMPORTANT**: Never commit actual credentials to version control

## Architecture

### Core Components

**Flask Application Structure:**
- `app.py` - Main Flask application with blueprint registration
- `routes/` - API endpoints organized by functionality:
  - `instances.py` - Instance management (list, details, actions)
  - `volumes.py` - Volume management (list, create, delete, extend, export)
  - `snapshots.py` - Snapshot management  
  - `ssh.py` - SSH connection management
  - `cloud.py` - Cloud environment management
- `models/openstack_manager.py` - Core OpenStack SDK integration with caching
- `models/ssh_model.py` - SSH connection database management
- `utils/` - Utility functions:
  - `cache.py` - Custom caching decorator
  - `error_handler.py` - Centralized error handling
  - `performance_logger.py` - Performance monitoring

### Key Design Patterns

**Multi-Environment Support:**
- Configured via `config.json` with multiple OpenStack clusters
- Each environment has separate Nova/Cinder clients
- Unified management interface across all environments

**Caching Strategy:**
- Instance and volume data cached with 1-second timeout
- Cache invalidated on write operations
- Custom `cache_with_timeout` decorator for API-level caching

**Error Handling:**
- Centralized error handling via `@error_handler` decorator
- Structured JSON error responses
- Comprehensive logging throughout

**Data Export:**
- Excel/CSV export functionality for instances and volumes
- Custom `CustomBytesIO` wrapper for Excel compatibility
- Pandas integration for data processing

## OpenStack Integration

The application uses OpenStack SDK clients:
- **Nova Client**: Instance management (start, stop, delete, etc.)
- **Cinder Client**: Volume operations (create, extend, snapshot)
- **Keystone**: Authentication across all environments

### Authentication Flow
1. Load credentials from `config.json`
2. Create Keystone sessions for each environment
3. Initialize Nova/Cinder clients with sessions
4. Handle connection failures gracefully

## Database

- **SQLite** for SSH connection management (`database/ssh_connections.db`)
- Tables managed via `ssh_model.py` with basic CRUD operations

## Security Features

- JWT token validation for sensitive operations
- Password protection for delete operations
- Configurable security settings in `config.json`
- **IMPORTANT**: All delete operations require password verification

## API Patterns

All API endpoints follow consistent patterns:
- JSON request/response format
- Standardized error responses
- Query parameter filtering and pagination
- Performance logging for all operations

### Common Parameters
- `cloud_name` - Target OpenStack environment
- `page`, `per_page` - Pagination
- `sort_by`, `sort_order` - Sorting
- Various filters per endpoint type

## Frontend Technology

- **Bootstrap 3** for UI framework
- **Font Awesome** for icons  
- **jQuery** for JavaScript functionality
- Single-page application consuming REST APIs

## Development Guidelines

### Adding New Features
1. Create route in appropriate blueprint
2. Add business logic to `openstack_manager.py`
3. Implement error handling and logging
4. Add caching if needed
5. Update frontend templates

### OpenStack Client Usage
- Always check client exists before operations
- Handle OpenStack exceptions gracefully
- Clear relevant caches after write operations
- Use consistent data formatting patterns

### Performance Considerations
- Leverage existing caching mechanisms
- Consider timeout implications for operations
- Use pagination for large datasets
- Monitor performance via `performance_logger`

## Current Limitations & Future Plans

As documented in `app/doc/需求.md`, the platform is planned for significant refactoring:
- Add authentication/authorization module
- Implement proper database layer
- Modern frontend framework migration
- Microservices architecture consideration

The current implementation serves as a foundational prototype for a comprehensive operations platform.
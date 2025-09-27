# RippleIt

A modern Flask web application for cloning and exploring remote Git repositories with a beautiful, responsive interface.

## Features

- 🌐 **Clone Remote Repositories**: Support for GitHub, GitLab, Bitbucket, and other Git hosting services
- 🔐 **Authentication Support**: Clone private repositories using username and access tokens
- 📁 **File Browser**: Interactive file and folder structure visualization
- 🎨 **Modern UI**: Beautiful, responsive design with smooth animations
- 🗂️ **Project Management**: View, manage, and delete cloned projects
- ⚡ **Fast & Lightweight**: Built with Flask for optimal performance

## Installation

1. **Clone or download this repository**
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the application**:
   ```bash
   python app.py
   ```
4. **Open your browser** and navigate to `http://localhost:5000`

## Usage

1. **Clone a Repository**:
   - Enter a Git repository URL (e.g., `https://github.com/username/repository.git`)
   - For private repositories, enter your username and access token
   - Click "Clone Repository"
   - Wait for the cloning process to complete

2. **Browse Projects**:
   - View all cloned projects on the Projects page
   - Click on any project to explore its file structure
   - Navigate through folders and view file information

3. **Manage Projects**:
   - Delete projects you no longer need
   - View project details and file sizes

## Requirements

- Python 3.7+
- Git (must be installed and available in PATH)
- Flask and dependencies (see requirements.txt)

## Project Structure

```
RippleIt/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/            # HTML templates
│   ├── base.html         # Base template with styling
│   ├── index.html        # Home page
│   ├── projects.html     # Projects listing page
│   └── project_view.html # Individual project view
└── cloned_projects/      # Directory for cloned repositories (created automatically)
```

## API Endpoints

- `GET /` - Home page with clone form
- `POST /clone` - Clone a repository
- `GET /projects` - List all projects
- `GET /project/<name>` - View specific project
- `GET /api/project/<name>/files` - Get project file structure (JSON)
- `POST /delete_project/<name>` - Delete a project

## Authentication

RippleIt supports cloning private repositories using username and access tokens:

- **GitHub**: Use your GitHub username and a Personal Access Token
- **GitLab**: Use your GitLab username and a Personal Access Token  
- **Bitbucket**: Use your Bitbucket username and an App Password
- **Other Git hosts**: Use the same username:token pattern

### Getting Access Tokens

- **GitHub**: Settings → Developer settings → Personal access tokens
- **GitLab**: User Settings → Access Tokens
- **Bitbucket**: Personal settings → App passwords

## Security Notes

- The application runs in debug mode by default (change for production)
- Cloned repositories are stored locally in the `cloned_projects` directory
- Access tokens are only used for cloning and are not stored
- Be cautious when cloning repositories from untrusted sources
- Consider implementing authentication for production use

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available under the MIT License.

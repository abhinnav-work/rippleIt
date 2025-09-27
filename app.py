from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import subprocess
import shutil
from pathlib import Path
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rippleit-secret-key'

# Create projects directory if it doesn't exist
PROJECTS_DIR = os.path.join(os.getcwd(), 'cloned_projects')
os.makedirs(PROJECTS_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/clone', methods=['POST'])
def clone_repository():
    try:
        git_url = request.json.get('git_url')
        username = request.json.get('username', '')
        access_token = request.json.get('access_token', '')
        
        if not git_url:
            return jsonify({'error': 'Git URL is required'}), 400
        
        # Extract repository name from URL
        repo_name = git_url.split('/')[-1].replace('.git', '')
        if not repo_name:
            repo_name = 'cloned_repo'
        
        # Create unique directory name
        clone_dir = os.path.join(PROJECTS_DIR, repo_name)
        counter = 1
        original_clone_dir = clone_dir
        while os.path.exists(clone_dir):
            clone_dir = f"{original_clone_dir}_{counter}"
            counter += 1
        
        # Prepare git clone command
        git_cmd = ['git', 'clone']
        
        # Add authentication if provided
        if username and access_token:
            # Modify URL to include credentials
            if 'github.com' in git_url:
                # For GitHub: https://username:token@github.com/owner/repo.git
                modified_url = git_url.replace('https://', f'https://{username}:{access_token}@')
            elif 'gitlab.com' in git_url:
                # For GitLab: https://username:token@gitlab.com/owner/repo.git
                modified_url = git_url.replace('https://', f'https://{username}:{access_token}@')
            elif 'bitbucket.org' in git_url:
                # For Bitbucket: https://username:token@bitbucket.org/owner/repo.git
                modified_url = git_url.replace('https://', f'https://{username}:{access_token}@')
            else:
                # For other Git hosts, try the same pattern
                modified_url = git_url.replace('https://', f'https://{username}:{access_token}@')
            
            git_cmd.append(modified_url)
        else:
            git_cmd.append(git_url)
        
        git_cmd.append(clone_dir)
        
        # Clone the repository
        result = subprocess.run(
            git_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            return jsonify({'error': f'Failed to clone repository: {result.stderr}'}), 400
        
        return jsonify({
            'success': True,
            'message': f'Repository cloned successfully to {clone_dir}',
            'project_name': os.path.basename(clone_dir),
            'project_path': clone_dir
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Clone operation timed out'}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/projects')
def list_projects():
    projects = []
    if os.path.exists(PROJECTS_DIR):
        for item in os.listdir(PROJECTS_DIR):
            item_path = os.path.join(PROJECTS_DIR, item)
            if os.path.isdir(item_path):
                projects.append({
                    'name': item,
                    'path': item_path
                })
    return render_template('projects.html', projects=projects)

@app.route('/project/<project_name>')
def view_project(project_name):
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return "Project not found", 404
    
    # Get directory structure
    structure = get_directory_structure(project_path)
    return render_template('project_view.html', 
                         project_name=project_name, 
                         structure=structure,
                         project_path=project_path)

@app.route('/api/project/<project_name>/files')
def get_project_files(project_name):
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404
    
    structure = get_directory_structure(project_path)
    return jsonify(structure)

@app.route('/api/project/<project_name>/file/<path:file_path>')
def get_file_content(project_name, file_path):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Construct full file path
        full_file_path = os.path.join(project_path, file_path)
        
        # Security check: ensure the file is within the project directory
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(project_path)):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(full_file_path) or not os.path.isfile(full_file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Check file size (limit to 1MB for performance)
        file_size = os.path.getsize(full_file_path)
        if file_size > 1024 * 1024:  # 1MB limit
            return jsonify({'error': 'File too large to display'}), 413
        
        # Read file content
        try:
            with open(full_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(full_file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except:
                return jsonify({'error': 'Cannot read file (binary or unsupported encoding)'}), 400
        
        # Get file extension for syntax highlighting
        file_extension = os.path.splitext(file_path)[1].lower()
        
        return jsonify({
            'content': content,
            'file_name': os.path.basename(file_path),
            'file_path': file_path,
            'file_size': format_file_size(file_size),
            'file_extension': file_extension,
            'line_count': len(content.splitlines())
        })
    
    except Exception as e:
        return jsonify({'error': f'Error reading file: {str(e)}'}), 500

def get_directory_structure(root_path, max_depth=3, current_depth=0):
    """Recursively get directory structure"""
    if current_depth >= max_depth:
        return None
    
    structure = []
    try:
        for item in sorted(os.listdir(root_path)):
            item_path = os.path.join(root_path, item)
            relative_path = os.path.relpath(item_path, PROJECTS_DIR)
            
            if os.path.isdir(item_path):
                # Skip hidden directories and common build/cache directories
                if item.startswith('.') and item not in ['.git']:
                    continue
                
                children = get_directory_structure(item_path, max_depth, current_depth + 1)
                structure.append({
                    'name': item,
                    'type': 'directory',
                    'path': relative_path,
                    'children': children
                })
            else:
                # Skip hidden files except important ones
                if item.startswith('.') and item not in ['.gitignore', '.env', '.env.example']:
                    continue
                
                file_size = os.path.getsize(item_path)
                structure.append({
                    'name': item,
                    'type': 'file',
                    'path': relative_path,
                    'size': format_file_size(file_size)
                })
    except PermissionError:
        pass
    
    return structure

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

@app.route('/delete_project/<project_name>', methods=['POST'])
def delete_project(project_name):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
            return jsonify({'success': True, 'message': 'Project deleted successfully'})
        else:
            return jsonify({'error': 'Project not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Failed to delete project: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

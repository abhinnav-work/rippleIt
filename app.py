from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import subprocess
import shutil
from pathlib import Path
import json
import xmltodict
import re

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
        branch = request.json.get('branch', '')
        
        if not git_url:
            return jsonify({'error': 'Git URL is required'}), 400
        
        # Extract repository name from URL
        repo_name = git_url.split('/')[-1].replace('.git', '')
        if not repo_name:
            repo_name = 'cloned_repo'
        
        # Create unique submodule name
        submodule_name = repo_name
        counter = 1
        original_submodule_name = submodule_name
        submodule_path = os.path.join(PROJECTS_DIR, submodule_name)
        
        # Check if submodule already exists in git index
        while os.path.exists(submodule_path) or is_submodule_in_index(submodule_path):
            # Try to cleanup if it exists in index but not on filesystem
            if not os.path.exists(submodule_path) and is_submodule_in_index(submodule_path):
                cleanup_submodule_from_index(submodule_path)
                break
            # If directory exists, try to remove it first
            elif os.path.exists(submodule_path):
                try:
                    shutil.rmtree(submodule_path)
                    break
                except:
                    pass
            submodule_name = f"{original_submodule_name}_{counter}"
            submodule_path = os.path.join(PROJECTS_DIR, submodule_name)
            counter += 1
        
        # Prepare git submodule add command with force flag
        git_cmd = ['git', 'submodule', 'add', '--force']
        
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
        
        # Add submodule path (use relative path)
        relative_submodule_path = os.path.relpath(submodule_path, os.getcwd())
        git_cmd.append(relative_submodule_path)
        
        # Initialize git repository if not already initialized
        if not os.path.exists('.git'):
            init_result = subprocess.run(
                ['git', 'init'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if init_result.returncode != 0:
                return jsonify({'error': f'Failed to initialize git repository: {init_result.stderr}'}), 400
        
        # Add the submodule
        result = subprocess.run(
            git_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            return jsonify({'error': f'Failed to add submodule: {result.stderr}'}), 400
        
        # Initialize and update the submodule
        submodule_init_result = subprocess.run(
            ['git', 'submodule', 'update', '--init', '--recursive', relative_submodule_path],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if submodule_init_result.returncode != 0:
            return jsonify({'error': f'Failed to initialize submodule: {submodule_init_result.stderr}'}), 400
        
        # Switch to specified branch if provided
        if branch:
            checkout_result = subprocess.run(
                ['git', 'checkout', branch],
                cwd=submodule_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if checkout_result.returncode != 0:
                # Try to fetch the branch from remote if it doesn't exist locally
                fetch_result = subprocess.run(
                    ['git', 'fetch', 'origin', branch],
                    cwd=submodule_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if fetch_result.returncode == 0:
                    checkout_result = subprocess.run(
                        ['git', 'checkout', branch],
                        cwd=submodule_path,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                
                if checkout_result.returncode != 0:
                    return jsonify({'error': f'Failed to checkout branch {branch}: {checkout_result.stderr}'}), 400
        
        # Get current branch information
        branch_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=submodule_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'
        
        return jsonify({
            'success': True,
            'message': f'Repository added as submodule to {submodule_path} on branch {current_branch}',
            'project_name': submodule_name,
            'project_path': submodule_path,
            'branch': current_branch
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Submodule operation timed out'}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/projects')
def list_projects():
    projects = []
    if os.path.exists(PROJECTS_DIR):
        for item in os.listdir(PROJECTS_DIR):
            item_path = os.path.join(PROJECTS_DIR, item)
            if os.path.isdir(item_path):
                # Get current branch
                branch_result = subprocess.run(
                    ['git', 'branch', '--show-current'],
                    cwd=item_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'
                
                projects.append({
                    'name': item,
                    'path': item_path,
                    'branch': current_branch
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

@app.route('/api/project/<project_name>/branch')
def get_project_branch(project_name):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Get current branch
        branch_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'
        
        return jsonify({'branch': current_branch})
    
    except Exception as e:
        return jsonify({'error': f'Error getting branch: {str(e)}'}), 500

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
        
        # Simple path construction - file_path should be relative to project root
        # Ensure proper path joining
        if file_path.startswith(project_name):
            # Remove project name prefix if it exists
            file_path = file_path[len(project_name):].lstrip('/\\')
        
        full_file_path = os.path.join(PROJECTS_DIR, project_name, file_path)
        
        # Debug logging
        print(f"DEBUG: project_name = {project_name}")
        print(f"DEBUG: file_path = {file_path}")
        print(f"DEBUG: full_file_path = {full_file_path}")
        print(f"DEBUG: exists = {os.path.exists(full_file_path)}")
        
        # Security check: ensure the file is within the project directory
        project_path_abs = os.path.abspath(project_path)
        full_file_path_abs = os.path.abspath(full_file_path)
        
        if not full_file_path_abs.startswith(project_path_abs):
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
    """Simple directory structure - folders first, then files"""
    if current_depth >= max_depth:
        return []
    
    directories = []
    files = []
    
    try:
        for item in sorted(os.listdir(root_path)):
            item_path = os.path.join(root_path, item)
            
            # Skip hidden files/dirs except important ones
            if item.startswith('.') and item not in ['.git', '.gitignore']:
                continue
            
            if os.path.isdir(item_path):
                children = get_directory_structure(item_path, max_depth, current_depth + 1)
                directories.append({
                    'name': item,
                    'type': 'directory',
                    'path': item,
                    'children': children
                })
            else:
                file_size = os.path.getsize(item_path)
                files.append({
                    'name': item,
                    'type': 'file',
                    'path': item,
                    'size': file_size
                })
    except PermissionError:
        pass
    
    # Return directories first, then files
    return directories + files

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

def is_submodule_in_index(submodule_path):
    """Check if a submodule path already exists in the git index"""
    try:
        # Convert to relative path for checking
        relative_path = os.path.relpath(submodule_path, os.getcwd())
        
        # Check if the path exists in .gitmodules
        if os.path.exists('.gitmodules'):
            with open('.gitmodules', 'r') as f:
                content = f.read()
                if relative_path in content:
                    return True
        
        # Check if the path exists in git index
        result = subprocess.run(
            ['git', 'ls-files', '--stage', relative_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 and result.stdout.strip() != ''
    except:
        return False

def cleanup_submodule_from_index(submodule_path):
    """Remove submodule from git index if it exists"""
    try:
        # Convert to relative path
        relative_path = os.path.relpath(submodule_path, os.getcwd())
        
        # Remove from git index
        subprocess.run(
            ['git', 'rm', '--cached', relative_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Try to deinitialize if it's a submodule
        subprocess.run(
            ['git', 'submodule', 'deinit', '-f', relative_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return True
    except:
        return False

@app.route('/update_project/<project_name>', methods=['POST'])
def update_project(project_name):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        relative_project_path = os.path.relpath(project_path, os.getcwd())
        
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Update the submodule to the latest commit
        update_result = subprocess.run(
            ['git', 'submodule', 'update', '--remote', relative_project_path],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if update_result.returncode != 0:
            return jsonify({'error': f'Failed to update submodule: {update_result.stderr}'}), 400
        
        # Get the latest commit hash
        commit_result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        commit_hash = commit_result.stdout.strip()[:8] if commit_result.returncode == 0 else 'unknown'
        
        return jsonify({
            'success': True,
            'message': f'Project updated successfully to commit {commit_hash}',
            'commit_hash': commit_hash
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Update operation timed out'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to update project: {str(e)}'}), 500

@app.route('/switch_branch/<project_name>', methods=['POST'])
def switch_branch(project_name):
    try:
        branch = request.json.get('branch')
        if not branch:
            return jsonify({'error': 'Branch name is required'}), 400
        
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Fetch all branches from remote
        fetch_result = subprocess.run(
            ['git', 'fetch', 'origin'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if fetch_result.returncode != 0:
            return jsonify({'error': f'Failed to fetch branches: {fetch_result.stderr}'}), 400
        
        # Check if branch exists locally
        branch_check = subprocess.run(
            ['git', 'branch', '-a'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if branch_check.returncode != 0:
            return jsonify({'error': f'Failed to list branches: {branch_check.stderr}'}), 400
        
        # Check if branch exists (local or remote)
        branches = branch_check.stdout
        if branch not in branches and f'origin/{branch}' not in branches:
            return jsonify({'error': f'Branch {branch} not found'}), 404
        
        # Switch to the branch
        if f'origin/{branch}' in branches and branch not in branches:
            # Create local branch tracking remote branch
            checkout_result = subprocess.run(
                ['git', 'checkout', '-b', branch, f'origin/{branch}'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            # Switch to existing local branch
            checkout_result = subprocess.run(
                ['git', 'checkout', branch],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
        
        if checkout_result.returncode != 0:
            return jsonify({'error': f'Failed to switch to branch {branch}: {checkout_result.stderr}'}), 400
        
        # Get current branch to confirm
        current_branch_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        current_branch = current_branch_result.stdout.strip() if current_branch_result.returncode == 0 else 'unknown'
        
        return jsonify({
            'success': True,
            'message': f'Switched to branch {current_branch}',
            'branch': current_branch
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Branch switch operation timed out'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to switch branch: {str(e)}'}), 500

@app.route('/get_branches/<project_name>')
def get_branches(project_name):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        
        # Fetch latest branches from remote
        subprocess.run(
            ['git', 'fetch', 'origin'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Get all branches (local and remote)
        branches_result = subprocess.run(
            ['git', 'branch', '-a'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if branches_result.returncode != 0:
            return jsonify({'success': False, 'error': f'Failed to list branches: {branches_result.stderr}'}), 400
        
        # Parse branches
        branches = []
        for line in branches_result.stdout.split('\n'):
            line = line.strip()
            if line and not line.startswith('*'):
                if line.startswith('remotes/origin/'):
                    branch_name = line.replace('remotes/origin/', '')
                    if branch_name != 'HEAD':
                        branches.append({
                            'name': branch_name,
                            'type': 'remote'
                        })
                elif not line.startswith('remotes/'):
                    branches.append({
                        'name': line,
                        'type': 'local'
                    })
        
        # Get current branch
        current_result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        current_branch = current_result.stdout.strip() if current_result.returncode == 0 else 'unknown'
        
        return jsonify({
            'success': True,
            'branches': [branch['name'] for branch in branches],
            'current_branch': current_branch
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to get branches: {str(e)}'}), 500

@app.route('/project/<project_name>/commits')
def view_commits(project_name):
    """View commits page for a project"""
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return "Project not found", 404
    
    return render_template('commits.html', project_name=project_name)

@app.route('/api/project/<project_name>/commits')
def get_commits(project_name):
    """Get commits for a project"""
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Get commits with detailed information
        commits_result = subprocess.run(
            ['git', 'log', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso', '--max-count=100'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if commits_result.returncode != 0:
            return jsonify({'error': f'Failed to get commits: {commits_result.stderr}'}), 400
        
        commits = []
        for line in commits_result.stdout.split('\n'):
            if line.strip():
                parts = line.split('|', 4)
                if len(parts) == 5:
                    commit_hash, author_name, author_email, date, message = parts
                    commits.append({
                        'hash': commit_hash,
                        'author_name': author_name,
                        'author_email': author_email,
                        'date': date,
                        'message': message,
                        'short_hash': commit_hash[:7]
                    })
        
        return jsonify({'success': True, 'commits': commits})
    
    except Exception as e:
        return jsonify({'error': f'Failed to get commits: {str(e)}'}), 500

@app.route('/project/<project_name>/visualize')
def visualize_project(project_name):
    """Visualize project structure page"""
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return "Project not found", 404
    
    return render_template('visualize.html', project_name=project_name)

@app.route('/project/<project_name>/analysis')
def analysis_project(project_name):
    """Project analysis page"""
    project_path = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_path):
        return "Project not found", 404
    
    return render_template('analysis.html', project_name=project_name)

@app.route('/api/project/<project_name>/visualize')
def get_project_visualization(project_name):
    """Get project structure for visualization"""
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Get project structure with file types and sizes
        structure = get_visualization_structure(project_path, project_name)
        
        # Get project statistics
        stats = get_project_stats(project_path)
        
        return jsonify({
            'success': True, 
            'structure': structure,
            'stats': stats
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get project visualization: {str(e)}'}), 500

@app.route('/api/project/<project_name>/analysis')
def get_project_analysis(project_name):
    """Get comprehensive project analysis"""
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({'error': 'Project not found'}), 404
        
        # Get comprehensive analysis
        analysis = {
            'android_analysis': get_android_analysis(project_path),
            'gradle_analysis': get_gradle_analysis(project_path),
            'manifest_analysis': get_manifest_analysis(project_path),
            'project_stats': get_project_stats(project_path),
            'lint_analysis': get_lint_analysis(project_path),
            'code_quality': get_code_quality_analysis(project_path),
            'security_analysis': get_security_analysis(project_path),
            'performance_analysis': get_performance_analysis(project_path)
        }
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to get project analysis: {str(e)}'}), 500

def get_visualization_structure(root_path, project_name, max_depth=4, current_depth=0):
    """Get project structure for visualization with recursive traversal"""
    if current_depth >= max_depth:
        return None
    
    structure = []
    try:
        # Get all items and separate directories and files
        all_items = os.listdir(root_path)
        directories = []
        files = []
        
        for item in all_items:
            item_path = os.path.join(root_path, item)
            relative_path = os.path.relpath(item_path, PROJECTS_DIR)
            
            if os.path.isdir(item_path):
                # Skip hidden directories and common build/cache directories
                if item.startswith('.') and item not in ['.git']:
                    continue
                
                # Recursively traverse into subdirectories
                children = get_visualization_structure(item_path, project_name, max_depth, current_depth + 1)
                directories.append({
                    'name': item,
                    'type': 'directory',
                    'path': relative_path,
                    'children': children,
                    'size': get_directory_size(item_path),
                    'file_count': count_files_in_directory(item_path)
                })
            else:
                # Skip hidden files except important ones
                if item.startswith('.') and item not in ['.gitignore', '.env', '.env.example']:
                    continue
                
                file_size = os.path.getsize(item_path)
                file_ext = os.path.splitext(item)[1].lower()
                file_type = get_file_type(file_ext)
                
                files.append({
                    'name': item,
                    'type': 'file',
                    'path': relative_path,
                    'size': file_size,
                    'extension': file_ext,
                    'file_type': file_type
                })
        
        # Sort directories and files separately, then combine (directories first)
        directories.sort(key=lambda x: x['name'].lower())
        files.sort(key=lambda x: x['name'].lower())
        
        # Add directories first, then files
        structure.extend(directories)
        structure.extend(files)
        
    except PermissionError:
        pass
    
    return structure

def count_files_in_directory(directory_path):
    """Count total files in directory (including subdirectories)"""
    count = 0
    try:
        for root, dirs, files in os.walk(directory_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') or d == '.git']
            count += len([f for f in files if not f.startswith('.') or f in ['.gitignore', '.env', '.env.example']])
    except (OSError, FileNotFoundError):
        pass
    return count

def get_directory_size(directory_path):
    """Calculate total size of directory"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, FileNotFoundError):
        pass
    return total_size

def get_file_type(extension):
    """Get file type category based on extension - optimized for Android projects"""
    type_mapping = {
        # Android-specific files
        '.kt': 'Kotlin',
        '.java': 'Java',
        '.xml': 'Android XML',
        '.gradle': 'Gradle',
        '.properties': 'Properties',
        '.pro': 'ProGuard',
        '.aidl': 'AIDL',
        '.rs': 'RenderScript',
        '.rsh': 'RenderScript Header',
        '.so': 'Native Library',
        '.aar': 'Android Archive',
        '.apk': 'Android Package',
        '.dex': 'Dalvik Executable',
        '.class': 'Java Class',
        '.jar': 'Java Archive',
        '.keystore': 'Android Keystore',
        '.jks': 'Java Keystore',
        '.p12': 'PKCS12 Keystore',
        '.pem': 'Certificate',
        '.crt': 'Certificate',
        '.cer': 'Certificate',
        '.pfx': 'PKCS12 Certificate',
        
        # Android resource files
        '.png': 'Android Drawable',
        '.jpg': 'Android Drawable',
        '.jpeg': 'Android Drawable',
        '.gif': 'Android Drawable',
        '.webp': 'Android Drawable',
        '.svg': 'Vector Drawable',
        '.9.png': 'Nine Patch',
        '.mp3': 'Android Raw',
        '.wav': 'Android Raw',
        '.ogg': 'Android Raw',
        '.mp4': 'Android Raw',
        '.avi': 'Android Raw',
        '.mkv': 'Android Raw',
        '.ttf': 'Android Font',
        '.otf': 'Android Font',
        '.woff': 'Android Font',
        '.woff2': 'Android Font',
        
        # Configuration files
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.toml': 'TOML',
        '.ini': 'Configuration',
        '.cfg': 'Configuration',
        '.conf': 'Configuration',
        '.env': 'Environment',
        '.gitignore': 'Git',
        '.gitattributes': 'Git',
        
        # Documentation
        '.md': 'Markdown',
        '.txt': 'Text',
        '.rst': 'reStructuredText',
        '.adoc': 'AsciiDoc',
        
        # Build and development
        '.sh': 'Shell Script',
        '.bat': 'Batch Script',
        '.ps1': 'PowerShell',
        '.dockerfile': 'Docker',
        '.lock': 'Lock File',
        '.example': 'Example',
        '.sample': 'Sample',
        
        # Other common files
        '.html': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'SASS',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.php': 'PHP',
        '.rb': 'Ruby',
        '.go': 'Go',
        '.rs': 'Rust',
        '.swift': 'Swift',
        '.scala': 'Scala',
        '.sql': 'SQL',
        '.cpp': 'C++',
        '.c': 'C',
        '.h': 'C/C++ Header',
        '.py': 'Python'
    }
    return type_mapping.get(extension, 'Other')

def get_project_stats(project_path):
    """Get enhanced project statistics with Android-specific analysis"""
    stats = {
        'total_files': 0,
        'total_directories': 0,
        'total_size': 0,
        'file_types': {},
        'largest_files': [],
        'android_analysis': get_android_analysis(project_path),
        'gradle_analysis': get_gradle_analysis(project_path),
        'manifest_analysis': get_manifest_analysis(project_path)
    }
    
    try:
        for root, dirs, files in os.walk(project_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') or d == '.git']
            
            stats['total_directories'] += len(dirs)
            
            for file in files:
                # Skip hidden files except important ones
                if file.startswith('.') and file not in ['.gitignore', '.env', '.env.example']:
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    stats['total_files'] += 1
                    stats['total_size'] += file_size
                    
                    # Track file types
                    ext = os.path.splitext(file)[1].lower()
                    file_type = get_file_type(ext)
                    stats['file_types'][file_type] = stats['file_types'].get(file_type, 0) + 1
                    
                    # Track largest files
                    stats['largest_files'].append({
                        'name': file,
                        'path': os.path.relpath(file_path, project_path),
                        'size': file_size
                    })
                except (OSError, FileNotFoundError):
                    pass
        
        # Sort largest files and keep top 10
        stats['largest_files'].sort(key=lambda x: x['size'], reverse=True)
        stats['largest_files'] = stats['largest_files'][:10]
        
    except (OSError, FileNotFoundError):
        pass
    
    return stats

def get_android_analysis(project_path):
    """Analyze Android-specific project structure"""
    analysis = {
        'has_android_manifest': False,
        'has_gradle_files': False,
        'has_kotlin_files': False,
        'has_java_files': False,
        'has_xml_resources': False,
        'has_native_code': False,
        'project_type': 'unknown',
        'build_system': 'unknown',
        'languages': [],
        'android_directories': []
    }
    
    try:
        # Check for Android-specific files and directories
        android_dirs = ['app', 'src', 'res', 'assets', 'libs', 'jni', 'cpp']
        gradle_files = ['build.gradle', 'build.gradle.kts', 'settings.gradle', 'gradle.properties']
        manifest_files = ['AndroidManifest.xml']
        
        for root, dirs, files in os.walk(project_path):
            # Check for Android directories
            for dir_name in dirs:
                if dir_name in android_dirs:
                    analysis['android_directories'].append(dir_name)
            
            # Check for specific files
            for file in files:
                if file in gradle_files:
                    analysis['has_gradle_files'] = True
                    analysis['build_system'] = 'gradle'
                elif file in manifest_files:
                    analysis['has_android_manifest'] = True
                elif file.endswith('.kt'):
                    analysis['has_kotlin_files'] = True
                    if 'Kotlin' not in analysis['languages']:
                        analysis['languages'].append('Kotlin')
                elif file.endswith('.java'):
                    analysis['has_java_files'] = True
                    if 'Java' not in analysis['languages']:
                        analysis['languages'].append('Java')
                elif file.endswith('.xml') and 'res' in root:
                    analysis['has_xml_resources'] = True
                elif file.endswith(('.cpp', '.c', '.h', '.so')):
                    analysis['has_native_code'] = True
                    if 'C/C++' not in analysis['languages']:
                        analysis['languages'].append('C/C++')
        
        # Determine project type
        if analysis['has_android_manifest'] and analysis['has_gradle_files']:
            analysis['project_type'] = 'android_app'
        elif analysis['has_gradle_files'] and not analysis['has_android_manifest']:
            analysis['project_type'] = 'android_library'
        elif analysis['has_java_files'] or analysis['has_kotlin_files']:
            analysis['project_type'] = 'java_project'
        else:
            analysis['project_type'] = 'general'
            
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def get_gradle_analysis(project_path):
    """Analyze Gradle build files"""
    analysis = {
        'gradle_files': [],
        'dependencies': [],
        'build_configs': {},
        'android_config': {},
        'has_kotlin_dsl': False
    }
    
    try:
        gradle_files = ['build.gradle', 'build.gradle.kts', 'settings.gradle', 'gradle.properties']
        
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file in gradle_files:
                    file_path = os.path.join(root, file)
                    analysis['gradle_files'].append(os.path.relpath(file_path, project_path))
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        # Check for Kotlin DSL
                        if file.endswith('.kts'):
                            analysis['has_kotlin_dsl'] = True
                        
                        # Extract dependencies
                        if 'dependencies' in content:
                            deps = extract_gradle_dependencies(content)
                            analysis['dependencies'].extend(deps)
                        
                        # Extract Android config
                        if 'android' in content:
                            android_config = extract_android_config(content)
                            analysis['android_config'].update(android_config)
                            
                    except (OSError, UnicodeDecodeError):
                        pass
                        
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def get_manifest_analysis(project_path):
    """Analyze AndroidManifest.xml"""
    analysis = {
        'package_name': '',
        'version_name': '',
        'version_code': '',
        'min_sdk': '',
        'target_sdk': '',
        'permissions': [],
        'activities': [],
        'services': [],
        'receivers': [],
        'providers': [],
        'features': []
    }
    
    try:
        manifest_path = os.path.join(project_path, 'app', 'src', 'main', 'AndroidManifest.xml')
        if not os.path.exists(manifest_path):
            # Try alternative paths
            for root, dirs, files in os.walk(project_path):
                if 'AndroidManifest.xml' in files:
                    manifest_path = os.path.join(root, 'AndroidManifest.xml')
                    break
        
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                # Parse XML
                manifest_dict = xmltodict.parse(content)
                manifest = manifest_dict.get('manifest', {})
                
                # Extract basic info
                analysis['package_name'] = manifest.get('@package', '')
                analysis['version_name'] = manifest.get('@android:versionName', '')
                analysis['version_code'] = manifest.get('@android:versionCode', '')
                
                # Extract uses-sdk
                uses_sdk = manifest.get('uses-sdk', {})
                if isinstance(uses_sdk, dict):
                    analysis['min_sdk'] = uses_sdk.get('@android:minSdkVersion', '')
                    analysis['target_sdk'] = uses_sdk.get('@android:targetSdkVersion', '')
                
                # Extract permissions
                permissions = manifest.get('uses-permission', [])
                if isinstance(permissions, list):
                    analysis['permissions'] = [p.get('@android:name', '') for p in permissions if isinstance(p, dict)]
                elif isinstance(permissions, dict):
                    analysis['permissions'] = [permissions.get('@android:name', '')]
                
                # Extract components
                application = manifest.get('application', {})
                if isinstance(application, dict):
                    # Activities
                    activities = application.get('activity', [])
                    if isinstance(activities, list):
                        analysis['activities'] = [a.get('@android:name', '') for a in activities if isinstance(a, dict)]
                    elif isinstance(activities, dict):
                        analysis['activities'] = [activities.get('@android:name', '')]
                    
                    # Services
                    services = application.get('service', [])
                    if isinstance(services, list):
                        analysis['services'] = [s.get('@android:name', '') for s in services if isinstance(s, dict)]
                    elif isinstance(services, dict):
                        analysis['services'] = [services.get('@android:name', '')]
                    
                    # Receivers
                    receivers = application.get('receiver', [])
                    if isinstance(receivers, list):
                        analysis['receivers'] = [r.get('@android:name', '') for r in receivers if isinstance(r, dict)]
                    elif isinstance(receivers, dict):
                        analysis['receivers'] = [receivers.get('@android:name', '')]
                    
                    # Providers
                    providers = application.get('provider', [])
                    if isinstance(providers, list):
                        analysis['providers'] = [p.get('@android:name', '') for p in providers if isinstance(p, dict)]
                    elif isinstance(providers, dict):
                        analysis['providers'] = [providers.get('@android:name', '')]
                
                # Extract features
                features = manifest.get('uses-feature', [])
                if isinstance(features, list):
                    analysis['features'] = [f.get('@android:name', '') for f in features if isinstance(f, dict)]
                elif isinstance(features, dict):
                    analysis['features'] = [features.get('@android:name', '')]
                    
            except Exception as e:
                print(f"Error parsing manifest: {e}")
                
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def extract_gradle_dependencies(content):
    """Extract dependencies from Gradle file content"""
    dependencies = []
    
    # Simple regex to extract dependencies
    dep_pattern = r"implementation\s+['\"]([^'\"]+)['\"]"
    test_dep_pattern = r"testImplementation\s+['\"]([^'\"]+)['\"]"
    android_dep_pattern = r"androidTestImplementation\s+['\"]([^'\"]+)['\"]"
    
    for pattern in [dep_pattern, test_dep_pattern, android_dep_pattern]:
        matches = re.findall(pattern, content)
        for match in matches:
            if ':' in match:  # Group:Artifact:Version format
                parts = match.split(':')
                if len(parts) >= 2:
                    dependencies.append({
                        'group': parts[0],
                        'artifact': parts[1],
                        'version': parts[2] if len(parts) > 2 else 'unknown',
                        'type': 'implementation'
                    })
    
    return dependencies

def extract_android_config(content):
    """Extract Android configuration from Gradle file"""
    config = {}
    
    # Extract compileSdkVersion
    compile_sdk_match = re.search(r'compileSdkVersion\s+(\d+)', content)
    if compile_sdk_match:
        config['compile_sdk'] = compile_sdk_match.group(1)
    
    # Extract minSdkVersion
    min_sdk_match = re.search(r'minSdkVersion\s+(\d+)', content)
    if min_sdk_match:
        config['min_sdk'] = min_sdk_match.group(1)
    
    # Extract targetSdkVersion
    target_sdk_match = re.search(r'targetSdkVersion\s+(\d+)', content)
    if target_sdk_match:
        config['target_sdk'] = target_sdk_match.group(1)
    
    # Extract buildToolsVersion
    build_tools_match = re.search(r'buildToolsVersion\s+["\']([^"\']+)["\']', content)
    if build_tools_match:
        config['build_tools'] = build_tools_match.group(1)
    
    return config

def get_lint_analysis(project_path):
    """Analyze code quality and linting issues"""
    analysis = {
        'total_issues': 0,
        'issues_by_severity': {'error': 0, 'warning': 0, 'info': 0},
        'issues_by_type': {},
        'common_issues': [],
        'file_issues': {},
        'recommendations': []
    }
    
    try:
        # Analyze Java/Kotlin files for common issues
        java_kotlin_files = []
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith(('.java', '.kt')):
                    java_kotlin_files.append(os.path.join(root, file))
        
        for file_path in java_kotlin_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                file_issues = []
                
                # Check for common issues
                if 'System.out.println' in content:
                    issue = {'type': 'warning', 'message': 'Use Log instead of System.out.println', 'line': content.count('System.out.println')}
                    file_issues.append(issue)
                    analysis['issues_by_type']['logging'] = analysis['issues_by_type'].get('logging', 0) + 1
                
                if 'TODO' in content or 'FIXME' in content:
                    issue = {'type': 'info', 'message': 'TODO/FIXME comments found', 'line': content.count('TODO') + content.count('FIXME')}
                    file_issues.append(issue)
                    analysis['issues_by_type']['todo'] = analysis['issues_by_type'].get('todo', 0) + 1
                
                if 'catch (Exception e)' in content:
                    issue = {'type': 'warning', 'message': 'Generic Exception catching', 'line': content.count('catch (Exception e)')}
                    file_issues.append(issue)
                    analysis['issues_by_type']['exception'] = analysis['issues_by_type'].get('exception', 0) + 1
                
                if 'new Thread(' in content:
                    issue = {'type': 'warning', 'message': 'Direct Thread creation', 'line': content.count('new Thread(')}
                    file_issues.append(issue)
                    analysis['issues_by_type']['threading'] = analysis['issues_by_type'].get('threading', 0) + 1
                
                if file_issues:
                    analysis['file_issues'][os.path.relpath(file_path, project_path)] = file_issues
                    analysis['total_issues'] += sum(issue['line'] for issue in file_issues)
                    
                    for issue in file_issues:
                        analysis['issues_by_severity'][issue['type']] += issue['line']
                        
            except (OSError, UnicodeDecodeError):
                pass
        
        # Generate recommendations
        if analysis['issues_by_type'].get('logging', 0) > 0:
            analysis['recommendations'].append('Replace System.out.println with Android Log class')
        if analysis['issues_by_type'].get('exception', 0) > 0:
            analysis['recommendations'].append('Use specific exception types instead of generic Exception')
        if analysis['issues_by_type'].get('threading', 0) > 0:
            analysis['recommendations'].append('Consider using AsyncTask or ExecutorService for background tasks')
        
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def get_code_quality_analysis(project_path):
    """Analyze code quality metrics"""
    analysis = {
        'complexity': {'high': 0, 'medium': 0, 'low': 0},
        'code_metrics': {
            'total_lines': 0,
            'code_lines': 0,
            'comment_lines': 0,
            'blank_lines': 0,
            'average_method_length': 0,
            'average_class_length': 0
        },
        'code_smells': [],
        'duplications': 0,
        'test_coverage': 0
    }
    
    try:
        total_methods = 0
        total_classes = 0
        method_lengths = []
        class_lengths = []
        
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith(('.java', '.kt')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        analysis['code_metrics']['total_lines'] += len(lines)
                        
                        for line in lines:
                            line = line.strip()
                            if not line:
                                analysis['code_metrics']['blank_lines'] += 1
                            elif line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                                analysis['code_metrics']['comment_lines'] += 1
                            else:
                                analysis['code_metrics']['code_lines'] += 1
                        
                        # Simple complexity analysis
                        content = ''.join(lines)
                        if content.count('if') + content.count('for') + content.count('while') + content.count('switch') > 10:
                            analysis['complexity']['high'] += 1
                        elif content.count('if') + content.count('for') + content.count('while') + content.count('switch') > 5:
                            analysis['complexity']['medium'] += 1
                        else:
                            analysis['complexity']['low'] += 1
                        
                        # Count methods and classes
                        methods = content.count('public ') + content.count('private ') + content.count('protected ')
                        classes = content.count('class ') + content.count('interface ')
                        
                        total_methods += methods
                        total_classes += classes
                        
                        if methods > 0:
                            method_lengths.append(len(lines) / methods)
                        if classes > 0:
                            class_lengths.append(len(lines) / classes)
                            
                    except (OSError, UnicodeDecodeError):
                        pass
        
        if total_methods > 0:
            analysis['code_metrics']['average_method_length'] = sum(method_lengths) / len(method_lengths)
        if total_classes > 0:
            analysis['code_metrics']['average_class_length'] = sum(class_lengths) / len(class_lengths)
        
        # Code smells detection
        if analysis['code_metrics']['average_method_length'] > 50:
            analysis['code_smells'].append('Long methods detected')
        if analysis['code_metrics']['average_class_length'] > 500:
            analysis['code_smells'].append('Large classes detected')
        if analysis['code_metrics']['comment_lines'] / max(analysis['code_metrics']['code_lines'], 1) < 0.1:
            analysis['code_smells'].append('Low comment density')
            
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def get_security_analysis(project_path):
    """Analyze security issues"""
    analysis = {
        'security_issues': [],
        'permissions_analysis': {'dangerous': [], 'normal': [], 'signature': []},
        'vulnerabilities': [],
        'security_score': 100
    }
    
    try:
        # Check for hardcoded secrets
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith(('.java', '.kt', '.xml', '.properties')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Check for hardcoded secrets
                        if 'password' in content.lower() and '=' in content:
                            analysis['security_issues'].append({
                                'type': 'warning',
                                'message': 'Potential hardcoded password',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['security_score'] -= 10
                        
                        if 'api_key' in content.lower() or 'apikey' in content.lower():
                            analysis['security_issues'].append({
                                'type': 'error',
                                'message': 'Hardcoded API key detected',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['security_score'] -= 20
                        
                        if 'http://' in content and 'https://' not in content:
                            analysis['security_issues'].append({
                                'type': 'warning',
                                'message': 'HTTP connection detected',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['security_score'] -= 5
                            
                    except (OSError, UnicodeDecodeError):
                        pass
        
        # Analyze permissions from manifest
        manifest_path = os.path.join(project_path, 'app', 'src', 'main', 'AndroidManifest.xml')
        if not os.path.exists(manifest_path):
            for root, dirs, files in os.walk(project_path):
                if 'AndroidManifest.xml' in files:
                    manifest_path = os.path.join(root, 'AndroidManifest.xml')
                    break
        
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for dangerous permissions
                dangerous_perms = [
                    'android.permission.CAMERA',
                    'android.permission.RECORD_AUDIO',
                    'android.permission.ACCESS_FINE_LOCATION',
                    'android.permission.READ_CONTACTS',
                    'android.permission.WRITE_CONTACTS',
                    'android.permission.READ_SMS',
                    'android.permission.SEND_SMS'
                ]
                
                for perm in dangerous_perms:
                    if perm in content:
                        analysis['permissions_analysis']['dangerous'].append(perm)
                        analysis['security_score'] -= 5
                        
            except (OSError, UnicodeDecodeError):
                pass
        
        analysis['security_score'] = max(0, analysis['security_score'])
        
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

def get_performance_analysis(project_path):
    """Analyze performance issues"""
    analysis = {
        'performance_issues': [],
        'memory_leaks': [],
        'ui_performance': [],
        'network_performance': [],
        'performance_score': 100
    }
    
    try:
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith(('.java', '.kt')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Check for performance issues
                        if 'findViewById' in content and content.count('findViewById') > 5:
                            analysis['performance_issues'].append({
                                'type': 'warning',
                                'message': 'Multiple findViewById calls',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['performance_score'] -= 5
                        
                        if 'new Bitmap' in content or 'BitmapFactory.decode' in content:
                            analysis['performance_issues'].append({
                                'type': 'info',
                                'message': 'Bitmap operations detected',
                                'file': os.path.relpath(file_path, project_path)
                            })
                        
                        if 'Thread.sleep' in content:
                            analysis['performance_issues'].append({
                                'type': 'warning',
                                'message': 'Thread.sleep in main thread',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['performance_score'] -= 10
                        
                        if 'while (true)' in content or 'for (;;)' in content:
                            analysis['performance_issues'].append({
                                'type': 'warning',
                                'message': 'Infinite loop detected',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['performance_score'] -= 15
                        
                        # Check for memory leaks
                        if 'static' in content and 'Context' in content:
                            analysis['memory_leaks'].append({
                                'type': 'warning',
                                'message': 'Static Context reference',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            analysis['performance_score'] -= 10
                        
                        # Check for UI performance issues
                        if 'setText' in content and content.count('setText') > 10:
                            analysis['ui_performance'].append({
                                'type': 'info',
                                'message': 'Frequent text updates',
                                'file': os.path.relpath(file_path, project_path)
                            })
                        
                        # Check for network performance
                        if 'HttpURLConnection' in content or 'OkHttp' in content:
                            analysis['network_performance'].append({
                                'type': 'info',
                                'message': 'Network operations detected',
                                'file': os.path.relpath(file_path, project_path)
                            })
                            
                    except (OSError, UnicodeDecodeError):
                        pass
        
        analysis['performance_score'] = max(0, analysis['performance_score'])
        
    except (OSError, FileNotFoundError):
        pass
    
    return analysis

@app.route('/update_all_projects', methods=['POST'])
def update_all_projects():
    try:
        # Update all submodules to latest
        update_result = subprocess.run(
            ['git', 'submodule', 'update', '--remote'],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for all projects
        )
        
        if update_result.returncode != 0:
            return jsonify({'error': f'Failed to update submodules: {update_result.stderr}'}), 400
        
        return jsonify({
            'success': True,
            'message': 'All projects updated successfully'
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Update operation timed out'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to update projects: {str(e)}'}), 500

@app.route('/delete_project/<project_name>', methods=['POST'])
def delete_project(project_name):
    try:
        project_path = os.path.join(PROJECTS_DIR, project_name)
        relative_project_path = os.path.relpath(project_path, os.getcwd())
        
        # Check if submodule exists in git index
        if not is_submodule_in_index(project_path):
            return jsonify({'error': 'Project not found in git index'}), 404
        
        # Remove submodule from git (even if directory doesn't exist)
        submodule_remove_result = subprocess.run(
            ['git', 'submodule', 'deinit', '-f', relative_project_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Continue even if deinit fails (directory might not exist)
        
        # Remove submodule from .gitmodules and .git/config
        submodule_rm_result = subprocess.run(
            ['git', 'rm', '-f', relative_project_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if submodule_rm_result.returncode != 0:
            return jsonify({'error': f'Failed to remove submodule: {submodule_rm_result.stderr}'}), 400
        
        # Remove the directory if it exists
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        
        return jsonify({'success': True, 'message': 'Submodule deleted successfully'})
    except Exception as e:
        return jsonify({'error': f'Failed to delete submodule: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

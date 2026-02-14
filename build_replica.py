import json
import re
import os

# Paths to the saved outputs from previous steps
STEP_16_PATH = r"C:/Users/Mars/.gemini/antigravity/brain/56525add-8f19-4a1f-9e69-50d9da68ddee/.system_generated/steps/16/output.txt"
STEP_29_PATH = r"C:/Users/Mars/.gemini/antigravity/brain/56525add-8f19-4a1f-9e69-50d9da68ddee/.system_generated/steps/29/output.txt"
OUTPUT_HTML_PATH = r"d:/Desktop/utils/team-manage-main/dash_replica.html"

def load_json_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Locate the start of the JSON object
    start_index = content.find('{')
    if start_index == -1:
        raise ValueError(f"No JSON start found in {path}")
    
    try:
        obj, _ = json.JSONDecoder().raw_decode(content[start_index:])
        return obj
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON from {path} starting at index {start_index}")
        # Debug: print a snippet
        print(content[start_index:start_index+100])
        raise e

print("Loading resource files...")
data_html = load_json_file(STEP_16_PATH)
data_assets = load_json_file(STEP_29_PATH)

html_content = data_html['html']
css_content = data_assets['css']
js_content = data_assets['js']

print("Injecting Mock Logic into JS...")
# Mock confirmRedeem
mock_redeem_logic = r"""
    // [ANTIGRAVITY MOCK] Simulate Network Request
    await new Promise(r => setTimeout(r, 800));
    console.log("[Mock] Redeem confirmed");
    
    const mockData = {
        success: true,
        message: '模拟兑换成功 (本地演示)',
        team_info: {
            team_name: 'GPT Team 模拟版',
            expires_at: '2026-12-31',
            subscription_plan: 'Pro',
            current_members: 8,
            max_members: 10
        }
    };
    showSuccessResult(mockData);
    return; // Skip real fetch
"""

# Replace the body of confirmRedeem function try block start
# We look for the fetch call and intercept it
js_content = re.sub(
    r'(async\s+function\s+confirmRedeem\s*\([^\)]*\)\s*\{[\s\S]*?try\s*\{)', 
    r'\1' + mock_redeem_logic, 
    js_content
)

# Mock Warranty Query
mock_warranty_query = r"""
            // [ANTIGRAVITY MOCK] Simulate Warranty Query
            await new Promise(r => setTimeout(r, 600));
            const mockData = {
                warranty_info: {
                    code: code,
                    remaining_days: 180,
                    used_by_email: 'demo@example.com',
                    used_at: '2025-01-01',
                    warranty_deadline: '2026-06-01',
                    warranty_redeem_count: 0,
                    can_warranty_redeem: true,
                    records: [{
                        email: 'demo@example.com',
                        redeemed_at: '2025-01-01 12:00:00',
                        is_warranty_redeem: false
                    }]
                }
            };
            resultDiv.innerHTML = renderWarrantyInfo(mockData.warranty_info, code);
            btn.disabled = false;
            btn.innerHTML = '<i data-lucide="search"></i> 查询质保状态';
            if (window.lucide) lucide.createIcons();
            return;
"""
js_content = re.sub(
    r'(const\s+res\s+=\s+await\s+fetch\s*\(\'/redeem/warranty/query\'[\s\S]*?body:\s*JSON\.stringify\(\{[\s\S]*?\}\)\s*\}\);)',
    mock_warranty_query + r'/* \1 */', # Comment out original
    js_content
)

print("Assembling HTML...")
# Replace CSS link - using string replace to avoid regex issues with backslashes in content
style_tag = f'<style>\n{css_content}\n</style>'
html_content = html_content.replace('<link rel="stylesheet" href="/static/css/user.css">', style_tag)

# Replace JS script
script_tag = f'<script>\n{js_content}\n</script>'
html_content = html_content.replace('<script src="/static/js/redeem.js"></script>', script_tag)

print(f"Writing to {OUTPUT_HTML_PATH}...")
with open(OUTPUT_HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Done!")

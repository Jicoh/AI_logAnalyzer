"""
配置 API 路由
处理 AI 配置的读取和更新
"""

from flask import Blueprint, request, jsonify

from src.config_manager.manager import ConfigManager
from src.utils import get_logger

logger = get_logger('config_api')

config_bp = Blueprint('config_api', __name__)

# 全局实例
config_manager = None


def get_config_manager():
    """获取或创建 ConfigManager 实例。"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager


@config_bp.route('/api/config', methods=['GET'])
def get_config():
    """获取当前 AI 配置。"""
    try:
        manager = get_config_manager()
        manager.reload()
        config = manager.get_all()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_bp.route('/api/config', methods=['POST'])
def update_config():
    """更新 AI 配置。"""
    try:
        data = request.get_json()
        manager = get_config_manager()

        # 更新 API 设置
        if 'api' in data:
            api_config = data['api']
            if 'base_url' in api_config:
                manager.set('api.base_url', api_config['base_url'])
            if 'api_key' in api_config and api_config['api_key']:
                manager.set('api.api_key', api_config['api_key'])
            if 'model' in api_config:
                manager.set('api.model', api_config['model'])
            if 'temperature' in api_config:
                manager.set('api.temperature', float(api_config['temperature']))
            if 'max_tokens' in api_config:
                manager.set('api.max_tokens', int(api_config['max_tokens']))

        # 更新 BM25 设置
        if 'bm25' in data:
            bm25_config = data['bm25']
            if 'k1' in bm25_config:
                manager.set('bm25.k1', float(bm25_config['k1']))
            if 'b' in bm25_config:
                manager.set('bm25.b', float(bm25_config['b']))

        # 更新 Embedding 设置
        if 'embedding' in data:
            emb_config = data['embedding']
            if 'enabled' in emb_config:
                manager.set('embedding.enabled', emb_config['enabled'])
            if 'provider' in emb_config:
                manager.set('embedding.provider', emb_config['provider'])
            if 'base_url' in emb_config:
                manager.set('embedding.base_url', emb_config['base_url'])
            if 'api_key' in emb_config:
                manager.set('embedding.api_key', emb_config['api_key'])
            if 'model' in emb_config:
                manager.set('embedding.model', emb_config['model'])
            if 'dimension' in emb_config:
                manager.set('embedding.dimension', int(emb_config['dimension']))
            if 'batch_size' in emb_config:
                manager.set('embedding.batch_size', int(emb_config['batch_size']))

        # 更新 Retrieval 设置
        if 'retrieval' in data:
            ret_config = data['retrieval']
            if 'mode' in ret_config:
                manager.set('retrieval.mode', ret_config['mode'])
            if 'bm25_weight' in ret_config:
                manager.set('retrieval.bm25_weight', float(ret_config['bm25_weight']))
            if 'vector_weight' in ret_config:
                manager.set('retrieval.vector_weight', float(ret_config['vector_weight']))
            if 'rrf_k' in ret_config:
                manager.set('retrieval.rrf_k', int(ret_config['rrf_k']))

        manager.save()

        return jsonify({'success': True, 'message': 'Configuration updated'})
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
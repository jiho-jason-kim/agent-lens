"""A local reservation workflow that recovers from stale cached inventory."""
import argparse
import json
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda, RunnableConfig
from langchain_core.tools import tool
from app.agent.openai_provider import ProviderConfigurationError
from app.config import provider_settings
from app.integrations.langchain_recorder import AgentLensRecorder


class StockUnavailable(ValueError):
    """The live inventory cannot satisfy this reservation."""


def run_reservation(*, mode='demo', store=None, model=None):
    if mode not in ('demo', 'live'):
        raise ValueError('Unknown workflow mode.')
    if model is None:
        if mode == 'demo':
            model = FakeListChatModel(responses=['The cached report was outdated. The first reservation failed. The alternative item was reserved successfully.'])
        else:
            settings = provider_settings()
            if not all(settings.values()):
                raise ProviderConfigurationError('Set OPENAI_API_KEY and OPENAI_MODEL in backend/.env.')
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(api_key=settings['OPENAI_API_KEY'], model=settings['OPENAI_MODEL'],
                               timeout=60, max_retries=0, max_completion_tokens=512, store=False)
    recorder = AgentLensRecorder('Stale inventory recovery', mode=mode)
    # This is a local fixture. The workflow never makes a real purchase or reservation.
    stock = {'camera': 0, 'camera-alternative': 2}

    @tool
    def cached_inventory(sku: str) -> dict:
        """Read yesterday's inventory report."""
        return {'sku': sku, 'available': 1, 'source': 'yesterday-cache'}

    @tool
    def live_inventory() -> dict:
        """Read the current local inventory fixture."""
        return dict(stock)

    @tool
    def reserve(sku: str) -> dict:
        """Reserve one item in the local inventory fixture."""
        if stock.get(sku, 0) < 1:
            raise StockUnavailable('The requested item is no longer available.')
        stock[sku] -= 1
        return {'sku': sku, 'reserved': True, 'remaining': stock[sku]}

    def execute(inputs: dict, config: RunnableConfig):
        dispatch_custom_event('inventory_before', {'state': dict(stock)}, config=config)
        report = cached_inventory.invoke({'sku': inputs['sku']}, config=config)
        try:
            result = reserve.invoke({'sku': report['sku']}, config=config)
        except StockUnavailable:
            current = live_inventory.invoke({}, config=config)
            dispatch_custom_event('recovery_decision', {
                'reason': 'Cached stock disagrees with current inventory.',
                'cached_report': report, 'current_inventory': current,
                'next_step': 'Reserve the configured alternative if stock is available.',
            }, config=config)
            if current['camera-alternative'] < 1:
                raise
            result = reserve.invoke({'sku': 'camera-alternative'}, config=config)
        dispatch_custom_event('inventory_after', {'state': dict(stock)}, config=config)
        summary = model.invoke([
            ('system', 'Summarize the provided local reservation result in two sentences. Do not invent actions.'),
            ('human', json.dumps({'cached_report': report, 'reservation': result,
                                 'recovered_from': 'StockUnavailable'})),
        ], config=config)
        return {'reservation': result, 'summary': summary}

    workflow = RunnableLambda(execute).with_config(run_name='reservation_workflow')
    try:
        workflow.invoke({'sku': 'camera'}, config={'callbacks': [recorder]})
    except Exception:
        # Callback errors are already recorded. Persist partial or failed runs for inspection.
        if not recorder.recording().events:
            raise
    return recorder.save(store)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('demo', 'live'), default='demo')
    options = parser.parse_args()
    run = run_reservation(mode=options.mode)
    print(f'{run.metadata.run_id}: {run.metadata.status}, {run.metadata.event_count} events')

import { render, screen } from '@testing-library/react';
import { DynamicCharts } from '../components/PageComponents/Procurement/DynamicCharts';
import { DynamicChart } from '../components/PageComponents/Procurement/DynamicChart';
import { Markdown } from '../components/Common/Markdown';
import type { ChartSpec, ChartType } from '../types';

function spec(type: ChartType, extra: Partial<ChartSpec> = {}): ChartSpec {
  return {
    id: `chart_${type}`,
    type,
    title: `Title ${type}`,
    rationale: `Why ${type}`,
    x_key: 'label',
    x_label: 'Category',
    y_label: 'Spend',
    unit: 'currency',
    series: [{ key: 'spend', name: 'Spend', color: '#86BC25' }],
    data: [
      { label: 'IT', spend: 600 },
      { label: 'HR', spend: 400 },
    ],
    ...extra,
  };
}

test('DynamicCharts renders title and rationale for each chart', () => {
  render(<DynamicCharts charts={[spec('hbar'), spec('line')]} currency="INR" />);
  expect(screen.getByText('Title hbar')).toBeInTheDocument();
  expect(screen.getByText('Why hbar')).toBeInTheDocument();
  expect(screen.getByText('Title line')).toBeInTheDocument();
});

test('DynamicCharts skips empty/invalid specs', () => {
  const empty = spec('bar', { data: [] });
  const { container } = render(<DynamicCharts charts={[empty]} currency="INR" />);
  expect(container.textContent).toBe('');
});

test.each<ChartType>(['bar', 'hbar', 'line', 'stacked_bar', 'grouped_bar', 'pie'])(
  'DynamicChart renders %s without throwing',
  (type) => {
    const multi = spec(type, {
      series: [
        { key: 'spend', name: 'A', color: '#86BC25' },
        { key: 'other', name: 'B', color: '#53565A' },
      ],
      data: [
        { label: 'IT', spend: 600, other: 120 },
        { label: 'HR', spend: 400, other: 80 },
      ],
    });
    expect(() => render(<DynamicChart spec={multi} currency="INR" />)).not.toThrow();
  },
);

test('DynamicChart waterfall (with total anchors) renders without throwing', () => {
  const wf = spec('waterfall', {
    series: [{ key: 'value', name: 'Variance', color: '#86BC25' }],
    data: [
      { label: 'Budget', value: 1000, is_total: true },
      { label: 'IT', value: 100 },
      { label: 'HR', value: -40 },
      { label: 'Actual', value: 1060, is_total: true },
    ],
  });
  expect(() => render(<DynamicChart spec={wf} currency="INR" />)).not.toThrow();
});

test('Markdown renders lists, headings, tables and links', () => {
  const md = [
    '## Key findings',
    '',
    '- First bullet',
    '- Second bullet',
    '',
    '| Category | Spend |',
    '| --- | --- |',
    '| IT | ₹600 |',
    '',
    'See [the report](https://example.com).',
  ].join('\n');

  const { container } = render(<Markdown>{md}</Markdown>);
  expect(container.querySelectorAll('li')).toHaveLength(2);
  expect(screen.getByText('First bullet')).toBeInTheDocument();
  expect(container.querySelector('table')).toBeTruthy();
  const link = screen.getByText('the report').closest('a');
  expect(link).toHaveAttribute('href', 'https://example.com');
  expect(link).toHaveAttribute('target', '_blank');
});

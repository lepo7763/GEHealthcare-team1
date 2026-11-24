import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    DEFAULT_CMS_PARAMS,
    toCmsQuery,
    summarizeCms,
} from '../src/pages/diagnostics/cmsParams.js';

const validParams = {
    start: {
        date: new Date(2026, 10, 19),
        time: '00:00:00.000',
    },
    end: {
        date: new Date(2026, 10, 19),
        time: '00:05:00.000',
    },
};

test('CMS generates correct API parameters', () => {
    const query = toCmsQuery(validParams);

    assert.equal(
        query.get('cms_start_datetime'),
        '2026-11-19T00:00:00.000'
    );

    assert.equal(
        query.get('cms_end_datetime'),
        '2026-11-19T00:05:00.000'
    );
});

test('CMS rejects missing dates', () => {
    assert.throws(
        () => toCmsQuery(DEFAULT_CMS_PARAMS),
        /valid CMS start/
    );
});

test('CMS rejects equal timestamps', () => {
    assert.throws(
        () => toCmsQuery({
            ...validParams,
            end: validParams.start,
        }),
        /after start/
    );
});

test('CMS rejects reversed timestamps', () => {
    assert.throws(
        () => toCmsQuery({
            ...validParams,
            end: {
                date: new Date(2026, 10, 18),
                time: '23:00:00.000',
            },
        }),
        /after start/
    );
});

test('CMS preserves millisecond precision', () => {
    const query = toCmsQuery({
        ...validParams,
        start: {
            ...validParams.start,
            time: '00:00:01.125',
        },
    });

    assert.equal(
        query.get('cms_start_datetime'),
        '2026-11-19T00:00:01.125'
    );
});

test('CMS produces a UTC review summary', () => {
    const summary = summarizeCms(validParams);

    assert.match(summary, /Nov 19, 2026/);
    assert.match(summary, /UTC/);
});
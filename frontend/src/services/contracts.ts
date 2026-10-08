import schemas from './backendSchemas.json'
// Validates the emitted Pydantic subset, not a general-purpose JSON Schema implementation.
// Unknown constraints fail closed; there is no value coercion or financial arithmetic.
type Schema = { [key: string]: unknown; $defs?: Record<string, Schema>; $ref?: string; anyOf?: Schema[]; oneOf?: Schema[]; patternProperties?: Record<string, Schema>; properties?: Record<string, Schema>; items?: Schema; required?: string[]; additionalProperties?: boolean | Schema; enum?: unknown[] }
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const supported = new Set(['$defs','$ref','title','description','default','type','const','enum','anyOf','properties','required','additionalProperties','items','minItems','maxItems','minLength','maxLength','pattern','format','minimum','maximum','exclusiveMinimum','exclusiveMaximum','readOnly','minProperties','maxProperties','oneOf','discriminator','patternProperties','ge','gt','le'])
const decimalPattern = '^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$'
const serializedDecimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/
export function validateWire<T>(name: keyof typeof schemas, value: unknown): T {
  const root = schemas[name] as Schema
  let nodes = 0
  function check(s: Schema, v: unknown, depth = 0): boolean {
    if (++nodes > 150000 || depth > 45 || Object.keys(s).some(k => !supported.has(k))) return false
    if (s.$ref) { const ref = s.$ref.split('/').pop()!; return !!root.$defs?.[ref] && check(root.$defs[ref], v, depth + 1) }
    if (s.anyOf && !s.anyOf.some(branch => check(branch, v, depth + 1))) return false
    if (s.oneOf && s.oneOf.filter(branch => check(branch, v, depth + 1)).length !== 1) return false
    if ('const' in s && v !== s.const || s.enum && !s.enum.includes(v)) return false
    if (s.type === 'null') return v === null
    if (s.type === 'string') {
      if (typeof v !== 'string' || v.length > 10000 || typeof s.minLength === 'number' && v.length < s.minLength || typeof s.maxLength === 'number' && v.length > s.maxLength) return false
      // Exact lexemes emitted by Pydantic Decimal serializers can use exponents.
      if (typeof s.pattern === 'string' && !(s.pattern === decimalPattern ? serializedDecimal : new RegExp(s.pattern)).test(v)) return false
      if (s.format === 'date-time' && (!/(?:Z|[+-]\d{2}:\d{2})$/.test(v) || !Number.isFinite(Date.parse(v)))) return false
      if (s.format === 'uuid' && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)) return false
      if (s.format === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false
      if (s.format && !['date-time','uuid','date'].includes(String(s.format))) return false
    }
    if (s.type === 'boolean' && typeof v !== 'boolean') return false
    if (s.type === 'number' || s.type === 'integer') {
      if (typeof v !== 'number' || !Number.isFinite(v) || s.type === 'integer' && !Number.isInteger(v)) return false
      if (typeof s.minimum === 'number' && v < s.minimum || typeof s.maximum === 'number' && v > s.maximum || typeof s.exclusiveMinimum === 'number' && v <= s.exclusiveMinimum || typeof s.exclusiveMaximum === 'number' && v >= s.exclusiveMaximum) return false
    }
    if (s.type === 'array') {
      if (!Array.isArray(v) || v.length > 2000 || typeof s.minItems === 'number' && v.length < s.minItems || typeof s.maxItems === 'number' && v.length > s.maxItems) return false
      if (!v.every(item => !s.items || check(s.items, item, depth + 1))) return false
    }
    if (s.type === 'object') {
      if (!object(v) || s.required?.some(k => !(k in v))) return false
      const keys = Object.keys(v)
      if (typeof s.minProperties === 'number' && keys.length < s.minProperties || typeof s.maxProperties === 'number' && keys.length > s.maxProperties) return false
      for (const key of keys) {
        const property = s.properties?.[key]
        const patterns = Object.entries(s.patternProperties ?? {}).filter(([pattern]) => new RegExp(pattern).test(key))
        if (property && !check(property, v[key], depth + 1) || patterns.some(([, schema]) => !check(schema, v[key], depth + 1))) return false
        if (!property && !patterns.length && (s.additionalProperties === false || object(s.additionalProperties) && !check(s.additionalProperties as Schema, v[key], depth + 1))) return false
      }
    }
    return true
  }
  if (!check(root, value)) throw new Error('Backend wire contract could not be verified.')
  return value as T
}

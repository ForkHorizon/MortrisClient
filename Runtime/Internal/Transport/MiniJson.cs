using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>A JSON number kept as its source text, because V7 types integers and floats by lexeme.</summary>
    internal readonly struct JsonNumber
    {
        internal JsonNumber(string lexeme) { Lexeme = lexeme; }
        internal string Lexeme { get; }
        public override string ToString() => Lexeme;
    }

    /// <summary>
    /// Strict, small JSON reader for data this SDK itself produced or a trusted server returned: objects become
    /// <c>Dictionary&lt;string,object&gt;</c> (duplicate keys rejected), arrays <c>List&lt;object&gt;</c>, numbers
    /// <see cref="JsonNumber"/>, everything else string / bool / null.
    /// </summary>
    internal static class MiniJson
    {
        private const int MaxDepth = 16;

        internal static object Parse(string json)
        {
            if (json == null) throw new ArgumentNullException(nameof(json));
            var reader = new Reader(json);
            var value = reader.ReadValue(0);
            reader.SkipWhitespace();
            if (!reader.AtEnd) throw new FormatException("Unexpected data after the JSON value at " + reader.Position + ".");
            return value;
        }

        internal static Dictionary<string, object> ParseObject(string json) =>
            Parse(json) as Dictionary<string, object> ?? throw new FormatException("JSON object expected.");

        internal static List<object> ParseArray(string json) =>
            Parse(json) as List<object> ?? throw new FormatException("JSON array expected.");

        internal static string Escape(string value)
        {
            var builder = new StringBuilder(value.Length + 2);
            builder.Append('"');
            foreach (var character in value)
            {
                switch (character)
                {
                    case '"': builder.Append("\\\""); break;
                    case '\\': builder.Append("\\\\"); break;
                    case '\b': builder.Append("\\b"); break;
                    case '\f': builder.Append("\\f"); break;
                    case '\n': builder.Append("\\n"); break;
                    case '\r': builder.Append("\\r"); break;
                    case '\t': builder.Append("\\t"); break;
                    default:
                        if (character < ' ') builder.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        else builder.Append(character);
                        break;
                }
            }
            return builder.Append('"').ToString();
        }

        private sealed class Reader
        {
            private readonly string _text;
            private int _position;

            internal Reader(string text) { _text = text; }
            internal bool AtEnd => _position >= _text.Length;
            internal int Position => _position;

            internal void SkipWhitespace()
            {
                while (_position < _text.Length && (_text[_position] == ' ' || _text[_position] == '\t' || _text[_position] == '\n' || _text[_position] == '\r'))
                    _position++;
            }

            internal object ReadValue(int depth)
            {
                if (depth > MaxDepth) throw new FormatException("JSON nesting is too deep.");
                SkipWhitespace();
                if (AtEnd) throw new FormatException("Unexpected end of JSON.");
                switch (_text[_position])
                {
                    case '{': return ReadObject(depth);
                    case '[': return ReadArray(depth);
                    case '"': return ReadString();
                    case 't': Expect("true"); return true;
                    case 'f': Expect("false"); return false;
                    case 'n': Expect("null"); return null;
                    default: return ReadNumber();
                }
            }

            private void Expect(string literal)
            {
                if (string.CompareOrdinal(_text, _position, literal, 0, literal.Length) != 0)
                    throw new FormatException("Invalid JSON literal at " + _position + ".");
                _position += literal.Length;
            }

            private Dictionary<string, object> ReadObject(int depth)
            {
                _position++;
                var result = new Dictionary<string, object>(StringComparer.Ordinal);
                SkipWhitespace();
                if (Peek() == '}') { _position++; return result; }
                while (true)
                {
                    SkipWhitespace();
                    if (Peek() != '"') throw new FormatException("Object key expected at " + _position + ".");
                    var key = ReadString();
                    SkipWhitespace();
                    if (Peek() != ':') throw new FormatException("':' expected at " + _position + ".");
                    _position++;
                    if (result.ContainsKey(key)) throw new FormatException("Duplicate JSON key '" + key + "'.");
                    result.Add(key, ReadValue(depth + 1));
                    SkipWhitespace();
                    var next = Peek();
                    _position++;
                    if (next == '}') return result;
                    if (next != ',') throw new FormatException("',' or '}' expected at " + (_position - 1) + ".");
                }
            }

            private List<object> ReadArray(int depth)
            {
                _position++;
                var result = new List<object>();
                SkipWhitespace();
                if (Peek() == ']') { _position++; return result; }
                while (true)
                {
                    result.Add(ReadValue(depth + 1));
                    SkipWhitespace();
                    var next = Peek();
                    _position++;
                    if (next == ']') return result;
                    if (next != ',') throw new FormatException("',' or ']' expected at " + (_position - 1) + ".");
                }
            }

            private char Peek() => _position < _text.Length ? _text[_position] : throw new FormatException("Unexpected end of JSON.");

            private string ReadString()
            {
                _position++;
                var builder = new StringBuilder();
                while (true)
                {
                    if (_position >= _text.Length) throw new FormatException("Unterminated JSON string.");
                    var character = _text[_position++];
                    if (character == '"') return builder.ToString();
                    if (character < ' ') throw new FormatException("Control character in JSON string.");
                    if (character != '\\') { builder.Append(character); continue; }
                    if (_position >= _text.Length) throw new FormatException("Unterminated JSON escape.");
                    var escape = _text[_position++];
                    switch (escape)
                    {
                        case '"': builder.Append('"'); break;
                        case '\\': builder.Append('\\'); break;
                        case '/': builder.Append('/'); break;
                        case 'b': builder.Append('\b'); break;
                        case 'f': builder.Append('\f'); break;
                        case 'n': builder.Append('\n'); break;
                        case 'r': builder.Append('\r'); break;
                        case 't': builder.Append('\t'); break;
                        case 'u':
                            if (_position + 4 > _text.Length ||
                                !int.TryParse(_text.Substring(_position, 4), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var code))
                                throw new FormatException("Invalid \\u escape.");
                            builder.Append((char)code);
                            _position += 4;
                            break;
                        default: throw new FormatException("Invalid JSON escape '\\" + escape + "'.");
                    }
                }
            }

            private JsonNumber ReadNumber()
            {
                var start = _position;
                if (_position < _text.Length && _text[_position] == '-') _position++;
                var digitsStart = _position;
                if (_position < _text.Length && _text[_position] == '0') _position++;
                else while (_position < _text.Length && _text[_position] >= '0' && _text[_position] <= '9') _position++;
                if (_position == digitsStart) throw new FormatException("Invalid JSON value at " + start + ".");
                if (_position < _text.Length && _text[_position] == '.')
                {
                    _position++;
                    var fraction = _position;
                    while (_position < _text.Length && _text[_position] >= '0' && _text[_position] <= '9') _position++;
                    if (_position == fraction) throw new FormatException("Invalid JSON fraction.");
                }
                if (_position < _text.Length && (_text[_position] == 'e' || _text[_position] == 'E'))
                {
                    _position++;
                    if (_position < _text.Length && (_text[_position] == '+' || _text[_position] == '-')) _position++;
                    var exponent = _position;
                    while (_position < _text.Length && _text[_position] >= '0' && _text[_position] <= '9') _position++;
                    if (_position == exponent) throw new FormatException("Invalid JSON exponent.");
                }
                return new JsonNumber(_text.Substring(start, _position - start));
            }
        }
    }
}

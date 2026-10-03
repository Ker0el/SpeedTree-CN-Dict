#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dict/translations.txt 格式校验。

按**运行时加载器**的解析规则检查词典，而不是按"看起来像什么"。

解析规则（与注入工具的实现保持一致）：
  1. 逐行处理；跳过空行和以 '#' 开头的行
  2. 分隔符 = 该行**第一个**不属于「空格 = 空格」形式的 '='
     —— 英文原文里本身就有 "Drag = brush" / "0.0 = bottom" 这种写法，
        无脑 split('=') 会把它们切坏
  3. key 去掉尾部空格，value 去掉首部空格
  4. key 或 value 为空的行丢弃
  5. 同名 key **后出现的覆盖前面的**
  6. key 区分大小写，精确全文匹配

用法：
    python tools/check_dict.py dict/translations.txt
    python tools/check_dict.py dict/translations.txt --quiet     # 只报告问题

退出码：0 = 没问题；1 = 有错误；2 = 有警告但无错误。
"""

import argparse
import collections
import sys


def _find_separator(line):
    """找第一个不属于「空格 = 空格」形式的 '='；找不到返回 -1。"""
    for i, ch in enumerate(line):
        if ch != "=":
            continue
        if i > 0 and i + 1 < len(line) and line[i - 1] == " " and line[i + 1] == " ":
            continue
        return i
    return -1


def parse(text):
    """返回 (最终映射, 每个键的出现记录, 最终生效行的行号, 计数)。"""
    entries = {}
    occurrences = collections.defaultdict(list)
    lineno_of = {}
    stats = collections.Counter()

    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r ").lstrip(" \t")
        if not line:
            stats["blank"] += 1
            continue
        if line[0] == "#":
            stats["comment"] += 1
            continue

        eq = _find_separator(line)
        if eq < 0:
            stats["no_separator"] += 1
            occurrences["\x00<no separator>"].append((lineno, line))
            continue

        key = line[:eq].rstrip(" ")
        value = line[eq + 1:].lstrip(" ")
        if not key or not value:
            stats["empty_side"] += 1
            continue

        stats["entry"] += 1
        occurrences[key].append((lineno, value))
        entries[key] = value
        lineno_of[key] = lineno

    return entries, occurrences, lineno_of, stats


def check(path, quiet):
    with open(path, "rb") as f:
        data = f.read()

    if data.startswith(b"\xef\xbb\xbf"):
        text = data.decode("utf-8-sig")
        bom = "UTF-8 with BOM"
    else:
        try:
            text = data.decode("utf-8")
            bom = "UTF-8 (no BOM)"
        except UnicodeDecodeError as e:
            print("ERROR  文件不是 UTF-8：%s" % e)
            return 1

    entries, occurrences, lineno_of, stats = parse(text)
    errors, warnings = [], []

    bad = occurrences.get("\x00<no separator>", [])
    if bad:
        errors.append("有 %d 行没有可用的分隔符 '='（会被整行丢弃）：" % len(bad))
        for lineno, line in bad[:5]:
            errors.append("    行%-5d %r" % (lineno, line[:90]))

    dups = {k: v for k, v in occurrences.items()
            if len(v) > 1 and not k.startswith("\x00")}
    conflicting = {k: v for k, v in dups.items() if len(set(x[1] for x in v)) > 1}

    for key, value in entries.items():
        for label, s in (("键", key), ("值", value)):
            for ch in s:
                if ord(ch) < 0x20 and ch != "\t":
                    errors.append("%s 含控制字符 U+%04X：%r" % (label, ord(ch), s[:70]))
                    break

    same = sorted(k for k, v in entries.items() if k == v)

    if not quiet:
        print("文件              %s" % path)
        print("编码              %s" % bom)
        print("字节              %d" % len(data))
        print("行数              %d" % (text.count("\n") + 1))
        print("  注释行          %d" % stats["comment"])
        print("  空行            %d" % stats["blank"])
        print("  有效映射        %d" % stats["entry"])
        print("唯一键            %d" % len(entries))
        print("重复出现的键      %d" % len(dups))
        print("  其中译文有冲突  %d  (后出现者生效)" % len(conflicting))
        print("键值完全相同的    %d  (多为专有名词，如 LOD / Phong)" % len(same))
        print()

    if conflicting:
        warnings.append("%d 个键有多个不同译文，最终生效的是**最后一条**：" % len(conflicting))
        for k, occ in sorted(conflicting.items(), key=lambda x: x[1][0][0])[:15]:
            warnings.append("    [%s]" % k)
            for lineno, value in occ:
                mark = " <-- 生效" if lineno == lineno_of[k] else ""
                warnings.append("        行%-5d %s%s" % (lineno, value[:70], mark))
        if len(conflicting) > 15:
            warnings.append("    ...（其余 %d 个省略）" % (len(conflicting) - 15))

    for w in warnings:
        print("WARN   " + w)
    for e in errors:
        print("ERROR  " + e)

    if errors:
        return 1
    if warnings:
        return 2
    if not quiet:
        print("OK     格式没问题。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="dict/translations.txt 格式校验")
    ap.add_argument("path", nargs="?", default="dict/translations.txt")
    ap.add_argument("--quiet", action="store_true", help="只报告问题，不打印统计")
    args = ap.parse_args()
    sys.exit(check(args.path, args.quiet))


if __name__ == "__main__":
    main()

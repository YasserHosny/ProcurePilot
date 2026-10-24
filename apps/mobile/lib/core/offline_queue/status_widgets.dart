import 'package:flutter/material.dart';

import '../theme/brand_colors.dart';

/// A shared "queued — will send when back online" confirmation banner.
///
/// Both the request form (T026) and the low-stock report screen (T032) show
/// this exact widget for a queued offline submission rather than each
/// inventing its own icon/text/key combination for the same state (FR-012 —
/// a queued item is never presented as confirmed).
class SubmissionQueuedBanner extends StatelessWidget {
  const SubmissionQueuedBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final warningColor =
        Theme.of(context).extension<LedgerColors>()?.warning ??
        const Color(0xFF8A4B00);

    return Column(
      key: const Key('submissionQueuedBanner'),
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Icon(
          Icons.schedule_outlined,
          key: const Key('submissionQueuedIcon'),
          color: warningColor,
          size: 64,
        ),
        const SizedBox(height: 16),
        Text(
          message,
          key: const Key('submissionQueuedMessage'),
          style: Theme.of(context).textTheme.titleLarge,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
